# このファイルは yfinance 1.5.2 の `screener/query.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: スクリーナーの条件式（QueryBase）。jfinance の EdinetQuery の土台
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: EquityQuery, FundQuery, ETFQuery（Yahoo の項目の条件式（EDINET の項目は jp/screener.py の EdinetQuery））
#   - 名前 yfinance → jfinance（import・ロガー名・repr）
#   - 差し替えた: Yahoo の項目の表を使わない

from abc import ABC, abstractmethod
import numbers
from typing import List, Union, Dict, TypeVar, Literal

from jfinance.exceptions import YFNotImplementedError
from ..utils import dynamic_docstring, generate_list_table_from_dict_universal

T = TypeVar('T', bound=Union[str, numbers.Real])

Operator = Literal['eq', 'is-in', 'btwn', 'gt', 'lt', 'gte', 'lte', 'and', 'or']

class QueryBase(ABC):
    def __init__(self, operator: Operator, operand: Union[ List['QueryBase'], List[str], List[numbers.Real] ]):
        operator = operator.upper()

        if not isinstance(operand, list):
            raise TypeError('Invalid operand type')
        if len(operand) <= 0:
            raise ValueError('Invalid field for EquityQuery')
            
        if operator == 'IS-IN':
            self._validate_isin_operand(operand)
        elif operator in {'OR','AND'}: 
            self._validate_or_and_operand(operand)
        elif operator == 'EQ': 
            self._validate_eq_operand(operand)
        elif operator == 'BTWN': 
            self._validate_btwn_operand(operand)
        elif operator in {'GT','LT','GTE','LTE'}: 
            self._validate_gt_lt(operand)
        else: 
            raise ValueError('Invalid Operator Value')

        self.operator = operator
        self.operands = operand

    @property
    @abstractmethod
    def valid_fields(self) -> Dict:
        raise YFNotImplementedError('valid_fields() needs to be implemented by child')

    @property
    @abstractmethod
    def valid_values(self) -> Dict:
        raise YFNotImplementedError('valid_values() needs to be implemented by child')

    def _validate_or_and_operand(self, operand: List['QueryBase']) -> None:
        if len(operand) <= 1: 
            raise ValueError('Operand must be length longer than 1')
        if all(isinstance(e, QueryBase) for e in operand) is False: 
            raise TypeError(f'Operand must be type {type(self)} for OR/AND')

    def _validate_eq_operand(self, operand: List[Union[str, numbers.Real]]) -> None:
        if len(operand) != 2:
            raise ValueError('Operand must be length 2 for EQ')
        
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)} "{operand[0]}"')
        if operand[0] in self.valid_values:
            vv = self.valid_values[operand[0]]
            if isinstance(vv, dict):
                # this data structure is slightly different to generate better docs, 
                # need to unpack here.
                vv = set().union(*[e for e in vv.values()])
            if operand[1] not in vv:
                raise ValueError(f'Invalid EQ value "{operand[1]}"')
    
    def _validate_btwn_operand(self, operand: List[Union[str, numbers.Real]]) -> None:
        if len(operand) != 3: 
            raise ValueError('Operand must be length 3 for BTWN')
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)}')
        if isinstance(operand[1], numbers.Real) is False:
            raise TypeError('Invalid comparison type for BTWN')
        if isinstance(operand[2], numbers.Real) is False:
            raise TypeError('Invalid comparison type for BTWN')

    def _validate_gt_lt(self, operand: List[Union[str, numbers.Real]]) -> None:
        if len(operand) != 2:
            raise ValueError('Operand must be length 2 for GT/LT')
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)} "{operand[0]}"')
        if isinstance(operand[1], numbers.Real) is False:
            raise TypeError('Invalid comparison type for GT/LT')

    def _validate_isin_operand(self, operand: List['QueryBase']) -> None:
        if len(operand) < 2:
            raise ValueError('Operand must be length 2+ for IS-IN')
        
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)} "{operand[0]}"')
        if operand[0] in self.valid_values:
            vv = self.valid_values[operand[0]]
            if isinstance(vv, dict):
                # this data structure is slightly different to generate better docs, 
                # need to unpack here.
                vv = set().union(*[e for e in vv.values()])
            for i in range(1, len(operand)):
                if operand[i] not in vv:
                    raise ValueError(f'Invalid EQ value "{operand[i]}"')

    def to_dict(self) -> Dict:
        op = self.operator
        ops = self.operands
        if self.operator == 'IS-IN':
            # Expand to OR of EQ queries
            op = 'OR'
            ops = [type(self)('EQ', [self.operands[0], v]) for v in self.operands[1:]]
        return {
            "operator": op,
            "operands": [o.to_dict() if isinstance(o, QueryBase) else o for o in ops]
        }

    def __repr__(self, indent=0) -> str:
        indent_str = "  " * indent
        class_name = self.__class__.__name__

        if isinstance(self.operands, list):
            # For list operands, check if they contain any QueryBase objects
            if any(isinstance(op, QueryBase) for op in self.operands):
                # If there are nested queries, format them with newlines
                operands_str = ",\n".join(
                    f"{indent_str}  {op.__repr__(indent + 1) if isinstance(op, QueryBase) else repr(op)}"
                    for op in self.operands
                )
                return f"{class_name}({self.operator}, [\n{operands_str}\n{indent_str}])"
            else:
                # For lists of simple types, keep them on one line
                return f"{class_name}({self.operator}, {repr(self.operands)})"
        else:
            # Handle single operand
            return f"{class_name}({self.operator}, {repr(self.operands)})"

    def __str__(self) -> str:
        return self.__repr__()


