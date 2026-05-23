"""CRT detection — generic state machine covering all 5 subtypes,
plus orthogonal Model #1 and Kiss of Death detectors."""

from crt.detector.kod import KODSignal, detect_kod
from crt.detector.model1 import Model1Signal, detect_model1, model1_to_signal
from crt.detector.state_machine import CRTDetector

__all__ = [
    "CRTDetector",
    "Model1Signal",
    "detect_model1",
    "model1_to_signal",
    "KODSignal",
    "detect_kod",
]
