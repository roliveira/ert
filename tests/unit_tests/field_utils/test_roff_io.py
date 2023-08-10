from io import StringIO
from textwrap import dedent

import hypothesis.strategies as st
import numpy as np
import pytest
from hypothesis import given

from ert.field_utils.roff_io import import_roff


@pytest.mark.parametrize("code_type", ["int", "byte"])
def test_coded_error_message(code_type):
    content = dedent(
        f"""roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 1
    int nY 1
    int nZ 1
    endtag
    tag parameter
    char name  "coded_parameter"
    array char codeNames 2
     "code_name_1"
     "code_name_2"
    array int codeValues 2
                0            1
    array {code_type} data 1
             0
    endtag
    tag eof
    endtag
    """
    )

    with pytest.raises(
        ValueError, match="Ert does not support discrete roff field parameters"
    ):
        _ = import_roff(StringIO(content), "coded_parameter")


@given(st.floats(width=32, allow_infinity=False, allow_nan=False))
def test_that_fetching_1_valued_parameter_fetches_correct_value(value):
    content = dedent(
        f"""roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 1
    int nY 1
    int nZ 1
    endtag
    tag parameter
    char name  "parameter"
    array float data 1
             {value}
    endtag
    tag eof
    endtag
    """
    )

    assert list(import_roff(StringIO(content), "parameter")) == pytest.approx([value])


def test_that_fetching_unknown_parameter_fails():
    content = dedent(
        """roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 1
    int nY 1
    int nZ 1
    endtag
    tag parameter
    char name  "parameter"
    array float data 1
             0.0
    endtag
    tag eof
    endtag
    """
    )

    with pytest.raises(
        ValueError, match="Could not find roff parameter 'does_not_exist' in"
    ):
        _ = import_roff(StringIO(content), "does_not_exist")


def test_that_unknown_dimensions_fail():
    content = dedent(
        """roff-asc
    #ROFF file#
    #Creator: Ert#
    tag parameter
    char name  "parameter"
    array float data 1
             0.0
    endtag
    tag eof
    endtag
    """
    )

    with pytest.raises(
        ValueError,
        match="Could not find dimensions for roff parameter 'parameter' in",
    ):
        _ = import_roff(StringIO(content), "parameter")


def test_that_undefined_values_are_masked():
    content = dedent(
        """roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 1
    int nY 1
    int nZ 1
    endtag
    tag parameter
    char name  "parameter"
    array float data 1
             -999.0
    endtag
    tag eof
    endtag
    """
    )

    values = import_roff(StringIO(content), "parameter")
    assert values[0, 0, 0] is np.ma.masked


@pytest.mark.parametrize("name, expected", [("parameter1", 1.0), ("parameter2", 2.0)])
def test_that_correct_named_parameter_is_fetched(name, expected):
    content = dedent(
        """roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 1
    int nY 1
    int nZ 1
    endtag
    tag parameter
    char name  "parameter1"
    array float data 1
             1.0
    endtag
    tag parameter
    char name  "parameter2"
    array float data 1
             2.0
    endtag
    tag eof
    endtag
    """
    )

    values = import_roff(StringIO(content), name)
    assert values[0, 0, 0] == expected


@pytest.mark.parametrize("name, expected", [("parameter1", 1.0), ("parameter2", 2.0)])
def test_that_correct_named_parameter_is_fetched_when_name_comes_last(name, expected):
    content = dedent(
        """roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 1
    int nY 1
    int nZ 1
    endtag
    tag parameter
    array float data 1
             1.0
    char name  "parameter1"
    endtag
    tag parameter
    array float data 1
             2.0
    char name  "parameter2"
    endtag
    tag eof
    endtag
    """
    )

    values = import_roff(StringIO(content), name)
    assert values[0, 0, 0] == expected


@pytest.mark.parametrize(
    "incorrect_dimensions", [(1, 2, 6), (6, 1, 2), (2, 2, 2), (6, 6, 6)]
)
def test_that_you_get_informative_error_message_for_incorrect_dimensions(
    incorrect_dimensions,
):
    content = dedent(
        f"""roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX {incorrect_dimensions[0]}
    int nY {incorrect_dimensions[1]}
    int nZ {incorrect_dimensions[2]}
    endtag
    tag parameter
    array float data 3
             1.0 2.0 3.0
    char name  "parameter"
    endtag
    tag eof
    endtag
    """
    )

    with pytest.raises(
        ValueError,
        match="Field parameter 'parameter' does not",
    ):
        _ = import_roff(StringIO(content), "parameter")


def test_that_once_parameter_and_dimensions_are_read_rest_of_file_is_not_considered():
    content = dedent(
        """roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 1
    int nY 1
    int nZ 1
    endtag
    tag parameter
    array float data 1
             1.0
    char name  "parameter"
    endtag
    tag parameter
    char name  "padded parameter"
    array float data 1
             2.0
    endtag
    tag parameter
    THIS IS NOT VALID ROFF FORMAT
    tag eof
    endtag
    """
    )

    assert import_roff(StringIO(content), "parameter")[0] == 1.0


def test_that_values_are_correctly_shaped():
    content = dedent(
        """roff-asc
    #ROFF file#
    #Creator: Ert#
    tag dimensions
    int nX 2
    int nY 2
    int nZ 2
    endtag
    tag parameter
    char name  "parameter"
    array float data 8
             1.0 2.0 3.0 4.0 5.0 6.0 7.0 8.0
    endtag
    tag eof
    endtag
    """
    )

    assert import_roff(StringIO(content), "parameter").tolist() == [
        [[2.0, 1.0], [4.0, 3.0]],
        [[6.0, 5.0], [8.0, 7.0]],
    ]