"""Lot 77 — jauge du cluster de production : couleurs, pourcentages, mesure avec client Motor simulé."""
import asyncio

import jauge_cluster as jc


def test_couleurs_aux_seuils():
    # Vert sous 45 %, orange dès 45 %, rouge dès 90 %
    assert jc.niveau(0.44) == "ok" and jc.niveau(0.45) == "attention" and jc.niveau(0.89) == "attention"
    assert jc.niveau(0.90) == "plein" and jc.niveau(1.0) == "plein"


def test_limite_par_defaut_et_variable(monkeypatch):
    monkeypatch.delenv("ATLAS_LIMITE_MO", raising=False)
    assert jc.synthese(1150.5, 10)["taille"]["limite_mo"] == 5120.0   # défaut : cluster Flex
    monkeypatch.setenv("ATLAS_LIMITE_MO", "512")                       # cluster gratuit M0
    assert jc.synthese(513.2, 10)["taille"]["niveau"] == "plein"
    monkeypatch.setenv("ATLAS_LIMITE_MO", "abc")                       # valeur illisible : défaut
    assert jc.synthese(100, 10)["taille"]["limite_mo"] == 5120.0


def test_synthese_prend_le_pire_des_deux_jauges(monkeypatch):
    monkeypatch.delenv("ATLAS_LIMITE_COLLECTIONS", raising=False)
    s = jc.synthese(1150.5, 500)
    assert s["taille"]["niveau"] == "ok" and s["collections"]["niveau"] == "plein"
    assert s["niveau"] == "plein" and s["pourcentage"] == 100.0


class _Base:
    """Base Motor simulée : dbStats + liste des collections."""
    def __init__(self, octets, collections):
        self.o, self.c = octets, collections

    async def command(self, nom):
        return {"dataSize": self.o, "indexSize": self.o}

    async def list_collection_names(self):
        return [f"c{i}" for i in range(self.c)]


class _Client:
    bases = {"site_meetafrican": _Base(100 * 1024 * 1024, 30), "sawali": _Base(50 * 1024 * 1024, 70)}

    async def list_database_names(self):
        return [*self.bases, "admin", "local"]

    def __getitem__(self, nom):
        return self.bases[nom]


def test_mesure_cumule_les_bases_et_ignore_les_internes():
    jc._cache.update(t=0.0, mesure=None)
    m = asyncio.run(jc.mesurer(_Client(), "site_meetafrican", forcer=True))
    assert m["taille"]["total_mo"] == 300.0 and m["collections"]["total"] == 100
    assert [b["nom"] for b in m["bases"]] == ["site_meetafrican", "sawali"] and m["bases"][0]["courante"] is True
