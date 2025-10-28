from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class WizardStockShare(models.TransientModel):
    _name = 'wizard.stock.share'
    _description = 'Wizard para ver stock compartido'

    # Mantengo product.template como pediste
    product_id = fields.Many2one(
        'product.template',
        string="Producto",
        help="Producto (template) para ver stock compartido",
        default=lambda self: self.env.context.get('default_product_id'),
        required=True,
    )

    # No uses default con search en O2M: usa compute
    line_stock_ids = fields.One2many(
        'stock.proveedor', 'product_id',
        string="Stocks Compartidos",
        help="Stocks compartidos desde otras instancias Odoo",
        compute='_compute_line_stock_ids',
        store=False,
    )

    @api.depends('product_id')
    def _compute_line_stock_ids(self):
        Proveedor = self.env['stock.proveedor']
        self._update_stock_safely(self.product_id.id)
        for wiz in self:
            wiz.line_stock_ids = Proveedor.search([('product_id', '=', wiz.product_id.id)]) if wiz.product_id else Proveedor.browse([])

    @api.model
    def default_get(self, fields_list):
        """Se ejecuta al abrir el wizard: actualiza remoto y refresca líneas."""
        res = super().default_get(fields_list)
        # Coaccionar a template_id y actualizar stock ANTES de crear el wizard
        pid = res.get('product_id') or self.env.context.get('default_product_id')
        if pid:
            pid = self._coerce_to_template_id(pid)
            res['product_id'] = pid
            self._update_stock_safely(pid)
        return res

    def action_update_stock(self):
        """Botón manual para refrescar stock desde el wizard."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Seleccione un producto."))
        self._update_stock_safely(self.product_id.id)
        # recompute líneas
        self._compute_line_stock_ids()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Stock actualizado"), 'type': 'success', 'sticky': False}
        }

    # ----------------- Helpers -----------------

    @api.model
    def _coerce_to_template_id(self, any_id: int) -> int:
        """Si llega un ID de product.product, conviértelo al template; si ya es template, devuélvelo."""
        if self.env['product.template'].browse(any_id).exists():
            product =  self.env['product.template'].browse(any_id)
            return product.id
        raise UserError(_("El ID %s no corresponde a product.template ni a product.product.") % any_id)

    @api.model
    def _update_stock_safely(self, product_tmpl_id: int):
        """Llama a res.company.update_stock_share_product(product_tmpl_id) con manejo de errores."""
        company = self.env.company  # ✅ correcto en Odoo 14+
        if not hasattr(company, 'update_stock_share_product'):
            raise UserError(_("No se encontró 'update_stock_share_product' en res.company (verifica el nombre/typo)."))
        try:
            if self.product_id.id_product_share:
                company.update_stock_share_product(self.product_id.id)  # ✅ nombre correcto
        except Exception as e:
            self.env.cr.rollback()
            raise UserError(_("Error al actualizar stock remoto: %s") % e)



class SaleOrder(models.Model):
    _inherit = 'sale.order.line'

    def action_view_stock (self):
        return {
            'name': 'Stock Compartido',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wizard.stock.share',
            'target': 'new',
            'context': {
                'default_product_id': self.product_id.product_tmpl_id.id,
            },
        }
