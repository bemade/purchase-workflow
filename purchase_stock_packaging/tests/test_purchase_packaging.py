# Copyright 2022 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestPurchasePackaging(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.line_obj = cls.env["purchase.order.line"]
        cls.partner = cls.env.ref("base.res_partner_12")
        cls.product = cls.env.ref("product.product_product_9")
        cls.packaging = cls.env["product.packaging"].create(
            {"name": "Test packaging", "product_id": cls.product.id, "qty": 5.0}
        )
        cls.packaging_10 = cls.env["product.packaging"].create(
            {"name": "Test packaging", "product_id": cls.product.id, "qty": 10.0}
        )
        cls.packaging_12 = cls.env["product.packaging"].create(
            {"name": "Test packaging 12", "product_id": cls.product.id, "qty": 12.0}
        )
        cls.env.user.groups_id += cls.env.ref("product.group_stock_packaging")
        cls.warehouse = cls.env.ref("stock.warehouse0")

    def test_purchase_packaging_from_procurement(self):
        # Check of packaging is well passed from procurement to purchase line
        # and does not take default one
        lines_before = self.line_obj.search([])
        self.group = self.env["procurement.group"].create({"name": "Test"})
        self.env["procurement.group"].run(
            [
                self.group.Procurement(
                    self.product,
                    20.0,
                    self.product.uom_id,
                    self.warehouse.lot_stock_id,
                    "Product",
                    "Product",
                    company_id=self.env.company,
                    values={"product_packaging_id": self.packaging},
                )
            ]
        )
        lines_after = self.line_obj.search([]) - lines_before

        self.assertTrue(lines_after.product_packaging_id)
        self.assertEqual(lines_after.product_packaging_id, self.packaging)

    def _po_line_from_move(self, qty, packaging):
        """Generate a PO line through the real make-to-order stock-move path,
        the way a sale order generates a purchase. Returns the new PO line."""
        lines_before = self.line_obj.search([])
        move = self.env["stock.move"].create(
            {
                "name": "Product Test",
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "location_id": self.warehouse.lot_stock_id.id,
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "product_packaging_id": packaging.id,
                "procure_method": "make_to_order",
            }
        )
        move._action_confirm()
        return self.line_obj.search([]) - lines_before

    def test_packaging_kept_on_qty_change(self):
        # Regression: once a PO line carries a procurement-supplied packaging
        # (propagated onto the destination stock move from the sale order
        # line), a later product_qty change -- e.g. a second procurement merged
        # into the same line, or a manual qty edit -- must NOT let the stored
        # compute overwrite that packaging with its own "biggest suitable"
        # suggestion. With 5/10/12 packagings present and a final qty of 20, the
        # suggestion would otherwise jump to the qty-10 packaging.
        line = self._po_line_from_move(5.0, self.packaging)
        self.assertEqual(line.product_packaging_id, self.packaging)
        # Simulate the qty change that the procurement-merge path performs.
        line.product_qty = 20.0
        self.assertEqual(
            line.product_packaging_id,
            self.packaging,
            "Procurement-supplied packaging must survive a later qty change",
        )

    def test_suggestion_still_fires_without_procurement_packaging(self):
        # AC2: when no packaging is supplied (manual PO line), the core
        # auto-suggestion behaviour must be unchanged: a qty of 20 with 5/10/12
        # packagings present suggests the biggest divisor (qty 10).
        po = self.env["purchase.order"].create({"partner_id": self.partner.id})
        line = self.line_obj.create(
            {
                "order_id": po.id,
                "product_id": self.product.id,
                "product_qty": 20.0,
                "product_uom": self.product.uom_id.id,
            }
        )
        self.assertEqual(
            line.product_packaging_id,
            self.packaging_10,
            "Auto-suggestion must be unchanged when no packaging is supplied",
        )
        # And it should keep tracking qty changes for non-procurement lines.
        line.product_qty = 12.0
        self.assertEqual(line.product_packaging_id, self.packaging_12)

    def test_packaging_qty_consistent(self):
        # AC3: the packaging quantity stays consistent with the kept packaging.
        lines_before = self.line_obj.search([])
        self.group = self.env["procurement.group"].create({"name": "Test qty"})
        self.env["procurement.group"].run(
            [
                self.group.Procurement(
                    self.product,
                    20.0,
                    self.product.uom_id,
                    self.warehouse.lot_stock_id,
                    "Product",
                    "Product",
                    company_id=self.env.company,
                    values={"product_packaging_id": self.packaging},
                )
            ]
        )
        line = self.line_obj.search([]) - lines_before
        self.assertEqual(line.product_packaging_id, self.packaging)
        # 20 units / 5-per-pack = 4 packs.
        self.assertEqual(line.product_packaging_qty, 4.0)

    def test_purchase_packaging_from_move(self):
        # Check of packaging is well passed from stock move to procurement,
        # then to purchase line and does not take default one
        lines_before = self.line_obj.search([])

        self.move = self.env["stock.move"].create(
            {
                "name": "Product Test",
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "location_id": self.warehouse.lot_stock_id.id,
                "product_id": self.product.id,
                "product_uom_qty": 20.0,
                "product_packaging_id": self.packaging.id,
                "procure_method": "make_to_order",
            }
        )

        self.move._action_confirm()

        lines_after = self.line_obj.search([]) - lines_before

        self.assertTrue(lines_after.product_packaging_id)
        self.assertEqual(lines_after.product_packaging_id, self.packaging)
