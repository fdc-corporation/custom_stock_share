{
    'name': 'Actualizacion de stock con otra instancia Odoo',
    'version': '1.0',
    'description': 'Configuracion para compartir stock entre diferentes instancias Odoo',
    'author': 'Yostin Palacios Calle',
    'website': '',
    'license': 'LGPL-3',
    'category': 'sale',
    'depends': [
        'base', 'sale', 'stock'
    ],
    'data': [
        'security/ir.model.access.csv',
        'view/view_almacen.xml',
        'view/view_product.xml',
        'view/view_sale.xml',
        'view/wizard_stock_proveedor.xml',
    ],
    'auto_install': False,
    'application': False,
}