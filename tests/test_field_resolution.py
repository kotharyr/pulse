from engineering_ops.services.fields import ResolutionError

def test_resolution_error_is_value_error():
    assert issubclass(ResolutionError, ValueError)
