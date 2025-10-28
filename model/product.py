from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    id_product_share = fields.Integer(string="ID Product Share", help="ID del producto en la instancia remota para compartir stock")
    stock_share_ids = fields.One2many('stock.proveedor', 'product_id', string="Stocks Compartidos", help="Stocks compartidos desde otras instancias Odoo")
