from pathlib import Path

from finance_app.portfolio import load_portfolio


def test_load_portfolio_reads_symbols_and_optional_position_fields(tmp_path: Path):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text(
        "Symbol,Current Price,Trade Date,Purchase Price,Quantity\n"
        "TSLA,345.13,20260422,350,100\n"
        "MSFT,481.15,,,\n",
        encoding="utf-8",
    )

    entries = load_portfolio(str(csv_file))

    assert [entry.symbol for entry in entries] == ["TSLA", "MSFT"]
    assert entries[0].purchase_price == 350.0
    assert entries[0].quantity == 100.0
    assert entries[1].purchase_price is None


def test_load_portfolio_deduplicates_symbols_using_latest_row(tmp_path: Path):
    csv_file = tmp_path / "portfolio.csv"
    csv_file.write_text("Symbol,Current Price\nMSFT,100\nmsft,200\n", encoding="utf-8")

    entries = load_portfolio(str(csv_file))

    assert len(entries) == 1
    assert entries[0].reference_price == 200.0
