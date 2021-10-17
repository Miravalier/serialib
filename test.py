#!/usr/bin/env python3
from example import *

print("Testing Alpha")
a = Alpha()
deserialized = Alpha.deserialize(a.serialize())
if a != deserialized:
    print("Test failed")
    raise RuntimeError
print("Alpha test succeeded")

print("Testing Beta")
b = Beta(
    aardvark=1234658, 
    buffalo="this is a string", 
    chinchilla=Color.WHITE,
    dinosaur=False,
    echidna=a
)
deserialized = Beta.deserialize(b.serialize())
if b != deserialized:
    print("Test failed")
    raise RuntimeError
print("Beta test succeeded")

print("Testing Gamma")
g = Gamma(
    asteroid=[1,2,3,4], 
    black_hole=["this", "is", "an", "array"],
    comet=[Color.WHITE, Color.BLACK, Color.BLUE],
    earth=[a] * 4
)
deserialized = Gamma.deserialize(g.serialize())
if g != deserialized:
    print("Test failed")
    raise RuntimeError
print("Gamma test succeeded")

print("Testing Zeta")
z = Zeta(austin_powers=Epsilon(altimeter=Delta(
    artist=[1235, 9865],
    baker=["a", "b", "c", "d"],
    chemist=[Color.ORANGE, Color.YELLOW, Color.GREEN, Color.RED, Color.BLUE, Color.BLACK],
    doctor=[True] * 8,
    engineer=[a] * 10
)))
deserialized = Zeta.deserialize(z.serialize())
if z != deserialized:
    print("Test failed")
    raise RuntimeError
print("Zeta test succeeded")
