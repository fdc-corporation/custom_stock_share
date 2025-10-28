from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class StockProveedor(models.Model):
    _name = 'stock.proveedor'

    proveedor = fields.Char(string="Proveedor", help="Nombre del proveedor asociado al almacen")
    product_id = fields.Many2one('product.template', string="Producto Asociado", help="Producto asociado al proveedor", default=lambda self: self.env.context.get('default_product_id'))
    cantidad_stock = fields.Integer(string="Cantidad en Stock", help="Cantidad de stock disponible del producto asociado")