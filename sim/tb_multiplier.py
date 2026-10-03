import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_multiplier_exhaustive(dut):
    """Exhaustive test: verify all signed 8-bit multiplication combinations"""
    
    # Loop through all possible values for a and b (-128 to 127)
    for a in range(-128, 128):
        for b in range(-128, 128):
            
            # Drive inputs
            dut.a_in.value = a
            dut.b_in.value = b
            
            # Wait for the output to settle
            await Timer(2, unit="ns")
            
            # Calculate expected and capture actual RTL output
            expected = a * b
            actual = dut.prod_out.value.signed_integer
            
            # Check result
            assert actual == expected, (
                f"Error: {a} * {b} failed! "
                f"Expected {expected}, got {actual}"
            )