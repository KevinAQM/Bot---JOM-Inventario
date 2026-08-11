import pytest
from services.schemas import AnalisisPizarra, ColumnaDia, ItemProduccion, CodigoProducto

def test_pydantic_schema_validation():
    """Prueba que el esquema Pydantic para Gemini valide correctamente los datos de la pizarra."""
    json_data = {
        "days": [
            {
                "day_header": "L",
                "date_str": "20-07",
                "is_worked_day": True,
                "items": [
                    {"code": "R", "quantity": 110},
                    {"code": "V", "quantity": 94},
                    {"code": "A", "quantity": 18},
                    {"code": "NC", "quantity": 63}
                ],
                "withdrawals": []
            },
            {
                "day_header": "M",
                "date_str": "21-07",
                "is_worked_day": True,
                "items": [
                    {"code": "R", "quantity": 109},
                    {"code": "V", "quantity": 82},
                    {"code": "A", "quantity": 24},
                    {"code": "NC", "quantity": 13}
                ],
                "withdrawals": []
            }
        ],
        "observations": "Pizarra clara y legible."
    }

    parsed = AnalisisPizarra.model_validate(json_data)
    assert len(parsed.days) == 2
    assert parsed.days[0].day_header == "L"
    assert parsed.days[0].items[0].code == CodigoProducto.ROJO
    assert parsed.days[0].items[0].quantity == 110
