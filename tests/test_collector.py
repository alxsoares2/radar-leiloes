import unittest
from bs4 import BeautifulSoup
from radar import category, parse_lot, payment_fields


class CollectorTests(unittest.TestCase):
    def test_auction_payment_is_independent_of_commission(self):
        fields = payment_fields(
            "DO PAGAMENTO - O arremate será pago por guia de depósito judicial. "
            "DA COMISSÃO - A comissão será paga por boleto. "
            "DA PROPOSTA - Interessados podem apresentar proposta de pagamento parcelado."
        )
        self.assertEqual(fields["payment"], "Guia judicial")
        self.assertEqual(fields["installment"], "Aceita proposta")
        self.assertEqual(fields["balanceBoleto"], "A confirmar")

    def test_express_rejection_beats_keyword(self):
        fields = payment_fields("Não serão aceitas propostas de pagamento parcelado.")
        self.assertEqual(fields["installment"], "Somente à vista")

    def test_extrajudicial_van_with_separate_event_heading(self):
        markup = """<h1>Leilão de Utilitários</h1><h1>FIAT DUCATO VAN 05/06</h1>
            ExtraJudicial Praça única Fechamento: 18/11/2026 às 10:36
            Próximo lance mínimo R$ 9.400,00 Ano Modelo 2006 Ano de Fabricação 2005"""
        lot = parse_lot(BeautifulSoup(markup, "html.parser"), "https://patiovitoriadaconquista.com/lote/ducato/3918", "Pátio")
        self.assertEqual((lot["category"], lot["mode"], lot["year"], lot["price"]), ("Van", "Extrajudicial", 2006, 9400))
        self.assertEqual(lot["end"], "2026-11-18T10:36:00-03:00")

    def test_vehicle_groups(self):
        for model, expected in [
            ("Carro Hyundai Creta", "SUV"), ("Caminhonete Hilux", "Caminhonete"),
            ("Veículo Chevrolet Vectra", "Carro"), ("Moto Honda", "Moto")
        ]:
            self.assertEqual(category(model), expected)

