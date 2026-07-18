from django.test import TestCase

from webprospects.scrapers.apmsl import parse_apmsl

SAMPLE = """
<html><body>
<div class="modal">
  <div class="modal-title">POLE DE SANTE DU MARAIS</div>
  <div class="modal-body">
    <img title="POLE DE SANTE DU MARAIS" alt="POLE DE SANTE DU MARAIS">
    8 rue de la garde<br>85300 SALLERTAINE<br><br>
    <strong>Num&eacute;ro Finess :</strong> 850026410<br>
    <strong>Date d'enregistrement Finess :</strong> 22/09/2016<br>
    <strong>Type de projet :</strong> Maison de Sant&eacute; Pluriprofessionnelle (MSP) multi-sites<br>
    <strong>Coordinateur(s) :</strong>
    <ul><li>ROUSSEAU St&eacute;phanie</li></ul>
    <strong>Team Leader(s) :</strong>
    <ul><li>ZINUTTI Marie</li></ul>
    <div class="entite-contact">
      <a href="mailto:poledesantedumarais@gmail.com"><span class="material-icons">alternate_email</span></a>
      <a href="www.polesantemarais.fr"><span class="material-icons">public</span></a>
      <a href="tel:0636863729"><span class="material-icons">phone_iphone</span> 06 36 86 37 29</a>
    </div>
  </div>
</div>
</body></html>
"""


class ApmslScraperTests(TestCase):
    def test_parses_single_record(self):
        records = parse_apmsl(SAMPLE)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["name"], "POLE DE SANTE DU MARAIS")
        self.assertEqual(r["address_line1"], "8 rue de la garde")
        self.assertEqual(r["postcode"], "85300")
        self.assertEqual(r["city"], "SALLERTAINE")
        self.assertEqual(r["finess_number"], "850026410")
        self.assertEqual(r["finess_date"], "22/09/2016")
        self.assertIn("multi-sites", r["project_type"])
        self.assertEqual(r["coordinators"], [{"first_name": "Stéphanie", "last_name": "Rousseau"}])
        self.assertEqual(r["team_leaders"], [{"first_name": "Marie", "last_name": "Zinutti"}])
        self.assertEqual(r["email"], "poledesantedumarais@gmail.com")
        self.assertEqual(r["phone"], "06 36 86 37 29")
        self.assertEqual(r["website"], "https://www.polesantemarais.fr")

    def test_name_from_modal_title_when_no_img(self):
        html = SAMPLE.replace('<img title="POLE DE SANTE DU MARAIS" alt="POLE DE SANTE DU MARAIS">', "")
        records = parse_apmsl(html)
        self.assertEqual(records[0]["name"], "POLE DE SANTE DU MARAIS")
