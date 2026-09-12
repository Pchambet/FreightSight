from app.domain.erp.urls import browser_base_url, odoo_record_url


def test_browser_base_url_rewrites_docker_host_for_local_demo() -> None:
    assert browser_base_url("http://host.docker.internal:8169/") == "http://localhost:8169"


def test_odoo_record_url_points_at_the_web_client() -> None:
    assert (
        odoo_record_url("http://host.docker.internal:8169", "fstest", "stock.landed.cost", 19)
        == "http://localhost:8169/web?db=fstest#id=19&model=stock.landed.cost"
    )
