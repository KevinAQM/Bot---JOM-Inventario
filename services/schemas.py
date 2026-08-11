from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class CodigoProducto(str, Enum):
    ROJO = "R"
    VERDE = "V"
    AMARILLO = "A"
    NO_COLOR = "NC"
    NEGRO = "N"

class ItemProduccion(BaseModel):
    code: CodigoProducto = Field(
        description="Código de color del producto: R (Rojo), V (Verde), A (Amarillo), NC (No color), N (Negro)"
    )
    quantity: int = Field(
        description="Cantidad entera producida leída de la pizarra (ej: si dice 'R-110' la cantidad es 110)"
    )

class RetiroClientePizarra(BaseModel):
    customer_name: str = Field(
        description="Nombre del cliente o nota escrito debajo de la producción (ej: 'Maria')"
    )
    code: CodigoProducto = Field(
        description="Código de producto retirado: R, V, A, NC, N"
    )
    quantity: int = Field(
        description="Cantidad retirada por el cliente"
    )

class ColumnaDia(BaseModel):
    day_header: str = Field(
        description="Letra o encabezado del día en la parte superior: L, M, M, J, V, S, D"
    )
    date_str: str = Field(
        description="Fecha escrita debajo de la letra en formato DD-MM (ejemplo: '20-07', '21-07', '22-07')"
    )
    is_worked_day: bool = Field(
        description="False si la columna está marcada con una 'X' grande o vacía sin producción. True si tiene registros de producción."
    )
    items: List[ItemProduccion] = Field(
        default_factory=list,
        description="Lista de ítems de producción registrados en la columna del día (ej: R-110, V-94, A-18, NC-63, N-150)"
    )
    withdrawals: List[RetiroClientePizarra] = Field(
        default_factory=list,
        description="Retiros o ventas a clientes anotados opcionalmente en la parte inferior de la columna"
    )

class AnalisisPizarra(BaseModel):
    days: List[ColumnaDia] = Field(
        description="Columnas de días de la semana parseadas de izquierda a derecha"
    )
    observations: Optional[str] = Field(
        default=None,
        description="Observaciones, notas sobre caligrafía difícil de leer o advertencias"
    )
