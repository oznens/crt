"""CRT detection — generic state machine covering all 5 subtypes,
plus orthogonal Model #1 and Kiss of Death detectors."""

from crt.detector.kod import KODSignal, detect_kod
from crt.detector.model1 import Model1Signal, detect_model1
from crt.detector.state_machine import CRTDetector

__all__ = [
    "CRTDetector",
    "Model1Signal",
    "detect_model1",
    "KODSignal",
    "detect_kod",
]
