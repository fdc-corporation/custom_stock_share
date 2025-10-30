from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import xmlrpc.client
import logging
import json
import requests
import base64, time

_logger = logging.getLogger(__name__)
BATCH = 100           # tamaño de página
RESIZE = '1024x1024'  # o '512x512' según tu necesidad


class ResCompany(models.Model):
    _inherit = 'res.company'

    
    url_instancia = fields.Char(string="URL Instancia", help="URL de la instancia Odoo con la que se sincroniza el stock")
    token_instancia = fields.Char(string="Token de autenticacion", help="Token de autenticacion para la instancia Odoo")
    db_name = fields.Char(string="Nombre de la base de datos", help="Nombre de la base de datos de la instancia Odoo")
    username_instancia = fields.Char(string="Usuario Instancia", help="Usuario para la instancia Odoo")
    password_instancia = fields.Char(string="Contraseña Instancia", help="Contraseña para la instancia Odoo")

    fields_exis = fields.Boolean(string="Campos Existentes", help="Indica si los campos necesarios ya existen en la instancia remota")
    id_warehouse_share = fields.Char(string="ID Almacen Share", help="ID del almacen en la instancia remota para compartir stock")
    

    def autenticacion_session (self, url, db, user, password):
        auth_url = f"{url}/web/session/authenticate"
        auth_payload = {
            "jsonrpc": "2.0",
            "params": {
                "db": db,
                "login": user,
                "password": password
            }
        }
        session = requests.Session()
        auth_response = session.post(auth_url, json=auth_payload)
        auth_data = auth_response.json()

        if not auth_data.get("result"):
            raise UserError("❌ Error al autenticar. Verifica credenciales y base de datos.")
        return session



    def action_create_fields(self):
        for record in self:
            if not record.url_instancia or not record.db_name or not record.username_instancia or not record.password_instancia:
                raise UserError("Por favor, complete todos los campos de configuracion antes de crear los campos en la instancia remota.")
            session = record.autenticacion_session(record.url_instancia, record.db_name, record.username_instancia, record.password_instancia)
            molde_id = self.get_model_id(record.url_instancia, record.username_instancia, record.password_instancia, session)
            field_produc_id = record.create_field(record.url_instancia, record.username_instancia, record.password_instancia, session, molde_id, "x_product_id_share", "integer", "Id product Share")

    def get_model_id (self, url, user, password, session):
        model_request = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": "ir.model",
                "method": "search_read",
                "args": [[["model", "=", "product.template"]], ["id"]],
                "kwargs":{"limit":1}
            },
            "id": 1,
        }
        resp = session.post(f"{url}/web/dataset/call_kw", json=model_request)
        model_id = resp.json()
        if not model_id.get("result"):
            raise UserError("❌ No se pudo obtener el ID del modelo product.template en la instancia remota.")
        model_id = model_id["result"][0]["id"]
        return model_id

    def create_field(self, url, user, password, session, model_id, field_name, field_type, field_label):
        existe_campo = self.validar_existencia_fields()
        if existe_campo:
            raise UserError(f"❌ El campo {field_name} ya existe en la instancia remota.")
            self.fields_exis = True
            return
        field_request = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": "ir.model.fields",
                "method": "create",
                "args": [{
                    "name": field_name,
                    "model_id": model_id,
                    "ttype": field_type,
                    "field_description": field_label,
                }],
                "kwargs": {}
            },
            "id": 1,
        }
        resp = session.post(f"{url}/web/dataset/call_kw", json=field_request)
        field_response = resp.json()
        if not field_response.get("result"):
            raise UserError(f"❌ No se pudo crear el campo {field_name} en la instancia remota.")
        if field_response['result']:
            self.fields_exis = True
        else :
            self.fields_exis = False
        return field_response["result"]

    def validar_existencia_fields(self):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": "ir.model.fields",
                "method": "search_read",
                "args": [[["name", "in", ["x_product_id_share"]]]],
                "kwargs": {}
            },
            "id": 1,
        }
        for record in self:
            if not record.url_instancia or not record.db_name or not record.username_instancia or not record.password_instancia:
                raise UserError("Por favor, complete todos los campos de configuracion antes de validar los campos en la instancia remota.")
            session = record.autenticacion_session(record.url_instancia, record.db_name, record.username_instancia, record.password_instancia)
            resp = session.post(f"{record.url_instancia}/web/dataset/call_kw", json=payload)
            response_data = resp.json()
            if response_data.get("result") and len(response_data["result"]) >= 1:
                record.fields_exis = True
            else:
                record.fields_exis = False


    def action_sync_products(self):
        for record in self:
            if not record.url_instancia  or not record.db_name or not record.username_instancia or not record.password_instancia:
                raise UserError("Por favor, complete todos los campos de configuracion antes de sincronizar los productos.")

            session = record.autenticacion_session(record.url_instancia, record.db_name, record.username_instancia, record.password_instancia)
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": "product.template",
                    "method": "search_read",
                    "args": [[["qty_available", ">", 0]]],
                    "kwargs": {"fields": ["id", "default_code", "qty_available"]}
                },
                "id": 1,
            }
            resp = session.post(f"{record.url_instancia}/web/dataset/call_kw", json=payload)
            response_data = resp.json()
            if not response_data.get("result"):
                raise UserError("❌ No se pudieron obtener los productos con stock disponible de la instancia remota.")
            productos = response_data["result"]
            list_product = []
            for producto in productos:
                codigo_interno = producto.get("default_code")
                product_share_id = producto.get("id")
                if codigo_interno:
                    producto_local = self.env['product.template'].search([('default_code', '=', codigo_interno)], limit=1)
                    if producto_local:
                        list_product.append(producto_local)
                        producto_local.id_product_share = product_share_id
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': f'{len(list_product)} fueron relacionados con los productos compartidos',
                    'type': 'success',
                    'sticky': False,
                }
            }

    def search_warehouse_stock(self, id_producto_share):
        for record in self:
            if not record.url_instancia or not record.db_name or not record.username_instancia or not record.password_instancia:
                raise UserError("Por favor, complete todos los campos de configuracion antes de buscar la ubicacion en la instancia remota.")
            session = record.autenticacion_session(record.url_instancia, record.db_name, record.username_instancia, record.password_instancia)
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": "stock.quant",
                    "method": "read_group",
                    "args": [[["warehouse_id", "=", int(record.id_warehouse_share)], ["product_tmpl_id", "=", int(id_producto_share)], ["location_id.usage", "=", "internal"]], ["inventory_quantity_auto_apply:sum"]],
                    "kwargs": {"lazy": False, "groupby": ["company_id"]}
                },
                "id": 1,
            }
            resp = session.post(f"{record.url_instancia}/web/dataset/call_kw", json=payload)
            response_data = resp.json()
            print(f"Respuesta de ubicacion de stock: {response_data}")
            if not response_data.get("result"):
                raise UserError("❌ No se pudo obtener stock en la instancia remota.")
            ubicacion = response_data["result"][0]
            print(f"Ubicacion de stock obtenida: {ubicacion}")
            return ubicacion

    def action_create_stock(self):
        session = self.autenticacion_session(self.url_instancia, self.db_name, self.username_instancia, self.password_instancia)

        if session:
            productos = self.env['product.template'].search([('id_product_share', '!=', False)])
            print(f"Productos con id_product_share: {productos}")
            for producto in productos:
                print("Buscando stock para producto:", producto.id_product_share)
                stock = self.search_warehouse_stock(producto.id_product_share)
                if stock.get('company_id'):
                    stock_provedor = self.env['stock.proveedor'].search([('proveedor', '=', stock.get('company_id')[1]), ('product_id', '=', producto.id)], limit=1)
                    if stock_provedor:
                        stock_provedor.cantidad_stock = stock.get('inventory_quantity_auto_apply', 0)
                    else:
                        self.env['stock.proveedor'].create({
                            'proveedor': stock.get('company_id')[1],
                            'product_id': producto.id,
                            'cantidad_stock': stock.get('inventory_quantity_auto_apply', 0)
                        })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Stock sincronizado correctamente desde la instancia remota.',
                    'type': 'success',
                    'sticky': False,
                }
            }

    def update_stock_share_product (self, id_product):
        for record in self:
            if not record.url_instancia or not record.db_name or not record.username_instancia or not record.password_instancia:
                raise UserError("Por favor, complete todos los campos de configuracion antes de buscar la ubicacion en la instancia remota.")
            session = record.autenticacion_session(record.url_instancia, record.db_name, record.username_instancia, record.password_instancia)
            product_local = self.env["product.template"].sudo().search([("id", "=", id_product)])
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": "stock.quant",
                    "method": "read_group",
                    "args": [[["warehouse_id", "=", int(record.id_warehouse_share)], ["product_tmpl_id", "=", product_local.id_product_share], ["location_id.usage", "=", "internal"]], ["inventory_quantity_auto_apply:sum"]],
                    "kwargs": {"lazy": False, "groupby": ["company_id"]}
                },
                "id": 1,
            }
            resp = session.post(f"{record.url_instancia}/web/dataset/call_kw", json=payload)
            response_data = resp.json()
            print(f"Respuesta de ubicacion de stock: {response_data}")
            if not response_data.get("result"):
                raise UserError("❌ No se pudo obtener stock en la instancia remota.")
            stock = response_data["result"][0]
            print(f"Ubicacion de stock obtenida: {stock}")
            if stock and stock.get('inventory_quantity_auto_apply', 0) > 0:
                stock_provedor = self.env['stock.proveedor'].search([('proveedor', '=', stock.get('company_id')[1]), ('product_id', '=', id_product)], limit=1)
                if stock_provedor:
                        stock_provedor.cantidad_stock = stock.get('inventory_quantity_auto_apply', 0)
                else:
                    self.env['stock.proveedor'].create({
                        'proveedor': stock.get('company_id')[1],
                        'product_id': producto.id,
                        'cantidad_stock': stock.get('inventory_quantity_auto_apply', 0)
                    })
    def _get_remote_image(self, session, base_url, model, rec_id, field, write_date=None, resize='1024x1024', timeout=60):
        """Intenta descargar /web/image por querystring y por path. Retorna bytes o None."""
        # Variante 1: querystring
        qs = {
            "model": model,
            "id": rec_id,
            "field": field,
        }
        if resize:
            qs["resize"] = resize
        if write_date:
            qs["unique"] = write_date  # cache-buster

        # 2 intentos por querystring
        for attempt in (1, 2):
            resp = session.get(f"{base_url}/web/image", params=qs, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp.content
            # 404 → imagen no existe; 500 → server error (corrupción/resize/etc.)
            # log breve:
            _ = resp.text[:300] if resp.text else ''
            print(f"  -> /web/image? ... intento {attempt}, status={resp.status_code}, body={_}")
            time.sleep(0.4)

        # Variante 2: path-style /web/image/model/id/field (algunos setups funcionan mejor)
        url_path = f"{base_url}/web/image/{model}/{rec_id}/{field}"
        if resize:
            url_path += f"/{resize}"
        # 2 intentos por path
        for attempt in (1, 2):
            resp = session.get(url_path, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp.content
            _ = resp.text[:300] if resp.text else ''
            print(f"  -> {url_path} intento {attempt}, status={resp.status_code}, body={_}")
            time.sleep(0.4)

        return None

    def get_img_product_share(self):
        sess = self.autenticacion_session(self.url_instancia, self.db_name, self.username_instancia, self.password_instancia)
        if not sess:
            raise UserError(_("No se pudo autenticar en la instancia remota."))

        BATCH = 80
        offset = total = 0

        while True:
            # 1) Trae solo ids/códigos/fecha (sin binarios)
            payload = {
                "jsonrpc": "2.0", "method": "call",
                "params": {
                    "model": "product.template",
                    "method": "search_read",
                    "args": [[["image_1920","!=",False], ["default_code","!=",False]]],
                    "kwargs": {"fields": ["id","default_code","write_date"], "limit": BATCH, "offset": offset},
                },
                "id": 1,
            }
            resp = sess.post(f"{self.url_instancia}/web/dataset/call_kw", json=payload, timeout=60)
            data = resp.json()
            rows = data.get("result") or []
            if not rows:
                break

            for rec in rows:
                pid = rec["id"]
                code = rec["default_code"]
                wdate = rec.get("write_date")
                print(f"  -> Descargando imagen para product.template ID {pid} (code {code})")
                local = self.env["product.template"].search([("default_code","=",code)], limit=1)
                if not local:
                    print("     Producto local no encontrado, se omite")
                    continue
                # 2) Intento con image_1920 redimensionada; si 500, usar tamaño menor o fallback por read
                content = self._get_remote_image(sess, self.url_instancia, "product.template", pid, "image_1920", wdate, resize="1024x1024")
                if content is None:
                    # fallback: tamaño menor
                    content = self._get_remote_image(sess, self.url_instancia, "product.template", pid, "image_1920", wdate, resize="512x512")

                if content is None:
                    # último fallback: JSON-RPC read de image_256 (más liviana)
                    read_payload = {
                        "jsonrpc": "2.0", "method": "call",
                        "params": {"model":"product.template","method":"read","args":[[pid],["default_code","image_256"]],"kwargs":{}},
                        "id": 2
                    }
                    r2 = sess.post(f"{self.url_instancia}/web/dataset/call_kw", json=read_payload, timeout=60).json()
                    rec2 = (r2.get("result") or [{}])[0]
                    img_b64 = rec2.get("image_256")
                    if img_b64:
                        content = base64.b64decode(img_b64)

                if not content:
                    print("     Código de estado: 500 (o sin contenido) - se omite")
                    continue

                # 3) Asignar en local
                local = self.env["product.template"].search([("default_code","=",code)], limit=1)
                print(f"     Asignando imagen al producto local ID {local.id if local else 'N/A'}")
                if local:
                    local.image_1920 = base64.b64encode(content)
                    total += 1

            self.env.cr.commit()
            offset += BATCH

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("✅ Imágenes sincronizadas: %s") % total, "type":"success", "sticky": False},
        }
