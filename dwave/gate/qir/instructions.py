# Copyright 2023 D-Wave Systems Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""QIR instructions, types and Operation transformations.

Contains the Instruction class and the dwave-gate to/from QIR operation transformations.
"""

__all__ = [
    "InstrType",
    "Operations",
    "Instruction",
]

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, NamedTuple, Optional, Sequence

import pyqir


class InstrType(Enum):
    base = auto()
    """Valid QIR base profile instructions"""

    external = auto()
    """Externally defined instructions. Falls back to decompositions if external
    functions are disallowed."""

    decompose = auto()
    """Decomposes operation into valid QIR instructions (or external if allowed)"""

    invalid = auto()
    """Invalid instructions that should raise an error if used"""

    skip = auto()
    """Instructions which are ignored when compiling to QIR (e.g., identity operation)"""

    measurement = auto()
    """Measurement instructions"""

    output = auto()
    """QIR output instructions"""


@dataclass
class Operations:
    """Dataclass containing operation transformations between QIR and ``dwave-gate``."""

    Op = NamedTuple("Op", [("type", InstrType), ("name", str)])

    to_qir = {
        "Identity": Op(InstrType.skip, "id"),
        "X": Op(InstrType.base, "x"),
        "Y": Op(InstrType.base, "y"),
        "Z": Op(InstrType.base, "z"),
        "Hadamard": Op(InstrType.base, "h"),
        "S": Op(InstrType.base, "s"),
        "T": Op(InstrType.base, "t"),
        "RX": Op(InstrType.base, "rx"),
        "RY": Op(InstrType.base, "ry"),
        "RZ": Op(InstrType.base, "rz"),
        "Rotation": Op(InstrType.external, "rot"),
        "CX": Op(InstrType.base, "cx"),
        "CY": Op(InstrType.external, "cy"),
        "CZ": Op(InstrType.base, "cz"),
        "SWAP": Op(InstrType.external, "swap"),
        "CHadamard": Op(InstrType.external, "ch"),
        "CRX": Op(InstrType.external, "crx"),
        "CRY": Op(InstrType.external, "cry"),
        "CRZ": Op(InstrType.external, "crz"),
        "CRotation": Op(InstrType.external, "crot"),
        "CSWAP": Op(InstrType.external, "cswap"),
        "CCX": Op(InstrType.external, "ccnot"),
        "Measurement": Op(InstrType.measurement, "mz"),
    }

    from_qir = {v[1]: k for k, v in to_qir.items()}

    from_qis_operation = {
        f"__quantum__qis__{tup[1]}__body": name
        for name, tup in to_qir.items()
        if tup.type not in (InstrType.decompose, InstrType.invalid)
    }

    # add special cases
    from_qis_operation.update(
        {
            "__quantum__qis__cnot__body": "CX",  # QIR uses CNOT instead of cx (PyQIR)
        }
    )


class Instruction:
    """Container class for QIR instructions.

    Args:
        type_: Instruction type.
        name: Name of the instruction to be applied.
        args: QIR arguments to instruction.
        external: Whether the operation is an external operation.
    """

    def __init__(
        self,
        type_: InstrType,
        name: str,
        args: Sequence[Any],
        external: Optional[pyqir.Function] = None,
    ) -> None:
        self._type = type_
        self._name = name

        self._assert_args(args)
        self._args = args

        if self.type is InstrType.external and not external:
            raise ValueError("Instruction with type 'external' missing external function.")

        self._external = external

    def _assert_args(self, args: Sequence[Any]) -> None:
        """Asserts that ``args`` only contain valid arguments.

        Args:
            args: Sequence of arguments to check.
        """
        for arg in args:
            if not isinstance(arg, (int, float, pyqir.Constant)):
                raise TypeError(f"Incorrect type {type(arg)} in arguments.")

    @property
    def name(self) -> str:
        """Instruction to apply."""
        return self._name

    @property
    def type(self) -> InstrType:
        """The instruction type."""
        return self._type

    @property
    def args(self) -> Sequence[Any]:
        """Optional arguments to instruction."""
        return self._args

    def execute(self, builder: pyqir.Builder) -> None:
        """Executes operation using the provided builder.

        Args:
            builder: PyQIR module builder.
        """
        if self._type in (InstrType.base, InstrType.measurement):
            self._execute_qis(builder)
        elif self._type is InstrType.external:
            self._execute_external(builder)
        else:
            raise TypeError(f"Cannot execute instruction of type '{self._type.name}'")

    def _execute_qis(self, builder: pyqir.Builder) -> None:
        """Executes QIS operation using the provided builder.

        Args:
            builder: PyQIR module builder.
        """
        getattr(pyqir.qis, self.name)(builder, *self.args)

    def _execute_external(self, builder: pyqir.Builder) -> None:
        """Executes external operation using the provided builder.

        Args:
            builder: PyQIR module builder.
        """
        builder.call(self._external, self.args)

    def __eq__(self, value: object) -> bool:
        """Whether two instructions are considered equal.

        Two instructions are considered equal if they have the same name, type,
        number of qubits and number of results.
        """
        eq_name = self.name == value.name
        eq_type = self.type == value.type

        num_qubits_self = [
            a.type.pointee.name == "Qubit" for a in self.args if isinstance(a, pyqir.Constant)
        ].count(True)

        num_qubits_value = [
            a.type.pointee.name == "Qubit" for a in value.args if isinstance(a, pyqir.Constant)
        ].count(True)

        num_results_self = [
            a.type.pointee.name == "Result" for a in self.args if isinstance(a, pyqir.Constant)
        ].count(True)

        num_results_value = [
            a.type.pointee.name == "Result" for a in value.args if isinstance(a, pyqir.Constant)
        ].count(True)

        parameters_self = [a for a in self.args if isinstance(a, (int, float))]
        parameters_value = [a for a in value.args if isinstance(a, (int, float))]

        eq_qubits = num_qubits_self == num_qubits_value
        eq_results = num_results_self == num_results_value
        eq_parameters = parameters_self == parameters_value

        if eq_name and eq_type and eq_qubits and eq_results and eq_parameters:
            return True
        return False
