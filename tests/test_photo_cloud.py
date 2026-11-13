import os
from unittest import TestCase
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

from cloud import cloud_database
from radar import lot_photos


class PhotoAndStorageTests(TestCase):
    def test_mega_only_accepts_images_of_the_same_lot(self):
        good = "https://cdn1.megaleiloes.com.br/batches/130026/car.jpg"
        page = BeautifulSoup(
            f'<img src="{good}"><img src="https://cdn1.megaleiloes.com.br/batches/2222/other.jpg"><img src="{good}">',
            "html.parser",
        )
        self.assertEqual(lot_photos(page, "https://www.megaleiloes.com.br/veiculos/creta-J130026"), [good])

    def test_patio_keeps_image_query(self):
        image = "/PHPs/photo.php?id=lotes_3918_car.jpeg&mode=main&wm=1"
        page = BeautifulSoup(f'<a href="{image}">Foto</a>', "html.parser")
        self.assertEqual(
            lot_photos(page, "https://patiovitoriadaconquista.com/lote/ducato/3918/"),
            ["https://patiovitoriadaconquista.com" + image],
        )

    @patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SECRET_KEY": "sb_secret_test"}, clear=True)
    @patch("cloud.requests.request")
    def test_snapshot_read_and_upsert(self, send):
        snapshot = {"lots": [], "sources": [], "boards": []}
        send.return_value = Mock(ok=True)
        send.return_value.json.return_value = [{"payload": snapshot}]
        database = cloud_database()
        self.assertEqual(database.read(), snapshot)
        database.save(snapshot)
        self.assertEqual(send.call_args.args[0], "POST")
        self.assertEqual(send.call_args.kwargs["json"], {"id": "main", "payload": snapshot})
        self.assertNotIn("Authorization", send.call_args.kwargs["headers"])

