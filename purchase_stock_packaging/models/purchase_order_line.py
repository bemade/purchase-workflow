# Copyright 2022 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    @api.model
    def _prepare_purchase_order_line_from_procurement(
        self,
        product_id,
        product_qty,
        product_uom,
        location_dest_id,
        name,
        origin,
        company_id,
        values,
        po,
    ):
        # For new PO lines we set the product packaging if present in
        # the procurement values.
        vals = super()._prepare_purchase_order_line_from_procurement(
            product_id,
            product_qty,
            product_uom,
            location_dest_id,
            name,
            origin,
            company_id,
            values,
            po,
        )
        if values.get("product_packaging_id"):
            vals["product_packaging_id"] = values.get("product_packaging_id").id
        return vals

    def _procurement_product_packaging(self):
        """Return the packaging carried over from the procurement (e.g. the
        originating sale order line), or an empty recordset.

        The packaging chosen upstream is propagated onto the destination stock
        move(s) that generated this purchase order line
        (``stock.rule._get_stock_move_values`` copies it from the procurement
        values). Reading it from there -- rather than from the line itself --
        gives a signal that persists across purchase-order-line writes, so a
        later ``product_qty`` change (e.g. a second procurement merged into the
        same line) cannot lose it.
        """
        self.ensure_one()
        moves = self.move_dest_ids or self.move_ids
        packagings = moves.product_packaging_id.filtered(
            lambda p: p.product_id == self.product_id
        )
        # Honour it only when the procurement is unambiguous about which
        # packaging to use.
        if len(packagings) == 1:
            return packagings
        return self.env["product.packaging"]

    @api.depends("product_id", "product_qty", "product_uom")
    def _compute_product_packaging_id(self):
        # When the packaging was supplied by the procurement (carried over from
        # the originating document, e.g. the sale order line), keep it: do not
        # let the core "biggest suitable packaging" suggestion overwrite the
        # packaging deliberately chosen upstream. This holds across later writes
        # (e.g. a product_qty change from a merged procurement), which would
        # otherwise re-trigger the compute and clobber the packaging. Lines
        # without a procurement-supplied packaging fall through to the standard
        # auto-suggestion behaviour, unchanged.
        from_procurement = self.browse()
        for line in self:
            procurement_packaging = line._procurement_product_packaging()
            if procurement_packaging:
                line.product_packaging_id = procurement_packaging
                from_procurement |= line
        rest = self - from_procurement
        return super(PurchaseOrderLine, rest)._compute_product_packaging_id()
