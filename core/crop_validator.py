import os
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional, Literal

Box = Tuple[int, int, int, int]  # (x1, y1, x2, y2)

RegionType = Literal[
    "face",
    "text",
    "speech_bubble",
    "object",
]

RenderDecision = Literal[
    "approved_crop",
    "contain_review",
    "contain_safe",
]

@dataclass(frozen=True)
class ProtectedRegion:
    x1: int
    y1: int
    x2: int
    y2: int
    region_type: RegionType
    confidence: float = 1.0
    label: str = ""

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def box(self) -> Box:
        return (self.x1, self.y1, self.x2, self.y2)


def box_width(box: Box) -> int:
    return max(0, box[2] - box[0])


def box_height(box: Box) -> int:
    return max(0, box[3] - box[1])


def box_area(box: Box) -> int:
    return box_width(box) * box_height(box)


def intersection_box(a: Box, b: Box) -> Optional[Box]:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def intersection_area(a: Box, b: Box) -> int:
    ibox = intersection_box(a, b)
    if ibox is None:
        return 0
    return box_area(ibox)


def containment_ratio(inner: Box, outer: Box) -> float:
    """Returns the fraction of 'inner' that lies inside 'outer' [0.0, 1.0]."""
    iarea = box_area(inner)
    if iarea == 0:
        return 0.0
    overlap = intersection_area(inner, outer)
    return overlap / float(iarea)


def expand_region(
    region: ProtectedRegion,
    image_width: int,
    image_height: int,
    margin_ratio: float = 0.15,
) -> ProtectedRegion:
    """Expands a protected region by margin_ratio (e.g. 15% padding for face/hair safety)."""
    w = region.width
    h = region.height
    margin_x = int(w * margin_ratio)
    margin_y = int(h * margin_ratio)
    return ProtectedRegion(
        x1=max(0, region.x1 - margin_x),
        y1=max(0, region.y1 - margin_y),
        x2=min(image_width, region.x2 + margin_x),
        y2=min(image_height, region.y2 + margin_y),
        region_type=region.region_type,
        confidence=region.confidence,
        label=region.label,
    )


def expand_box_safely(
    box: Box,
    image_width: int,
    image_height: int,
    neighboring_boxes: Optional[List[Box]] = None,
    margin_ratio: float = 0.06,
) -> Box:
    """
    Expands a crop candidate by margin_ratio while preventing expansion into neighboring panels.
    """
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    margin_x = max(1, int(w * margin_ratio))
    margin_y = max(1, int(h * margin_ratio))

    proposed = (
        max(0, x1 - margin_x),
        max(0, y1 - margin_y),
        min(image_width, x2 + margin_x),
        min(image_height, y2 + margin_y),
    )

    if not neighboring_boxes:
        return proposed

    px1, py1, px2, py2 = proposed
    for neighbor in neighboring_boxes:
        nx1, ny1, nx2, ny2 = neighbor

        # Check vertical overlap to constrain horizontal expansion
        vertical_overlap = min(py2, ny2) - max(py1, ny1)
        if vertical_overlap > 0:
            if nx2 <= x1 and px1 < nx2:
                px1 = max(px1, nx2)
            if nx1 >= x2 and px2 > nx1:
                px2 = min(px2, nx1)

        # Check horizontal overlap to constrain vertical expansion
        horizontal_overlap = min(px2, nx2) - max(px1, nx1)
        if horizontal_overlap > 0:
            if ny2 <= y1 and py1 < ny2:
                py1 = max(py1, ny2)
            if ny1 >= y2 and py2 > ny1:
                py2 = min(py2, ny1)

    return (
        max(0, int(px1)),
        max(0, int(py1)),
        min(image_width, int(px2)),
        min(image_height, int(py2)),
    )


@dataclass
class RegionSafetyResult:
    safe: bool
    region: ProtectedRegion
    containment: float
    reason: str


def validate_protected_region(
    crop: Box,
    region: ProtectedRegion,
    minimum_containment: float = 0.98,
) -> RegionSafetyResult:
    """Checks if a protected region (face, text) is safely inside the crop."""
    ratio = containment_ratio(region.box, crop)
    safe = ratio >= minimum_containment
    if safe:
        reason = f"{region.region_type} fully contained ({ratio:.2f})"
    else:
        reason = f"{region.region_type} is clipped (containment={ratio:.3f})"

    return RegionSafetyResult(
        safe=safe,
        region=region,
        containment=ratio,
        reason=reason,
    )


@dataclass
class DetectionCoverage:
    ocr_attempted: bool = False
    ocr_completed: bool = False
    face_detection_attempted: bool = False
    face_detection_completed: bool = False
    ocr_confidence: float = 0.0
    face_confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def quality_score(self, require_ocr: bool, require_face: bool) -> float:
        required_scores = []
        if require_ocr:
            if not (self.ocr_attempted and self.ocr_completed):
                return 0.0
            required_scores.append(self.ocr_confidence)

        if require_face:
            if not (self.face_detection_attempted and self.face_detection_completed):
                return 0.0
            required_scores.append(self.face_confidence)

        if not required_scores:
            return 1.0
        return min(required_scores)


@dataclass
class CoverageGateResult:
    passed: bool
    failures: List[str]
    warnings: List[str]


def check_detection_coverage(
    coverage: DetectionCoverage,
    require_ocr: bool = True,
    require_face: bool = True,
) -> CoverageGateResult:
    failures = []
    warnings = []
    if require_ocr:
        if not coverage.ocr_attempted:
            failures.append("OCR was not attempted")
        elif not coverage.ocr_completed:
            failures.append("OCR did not complete successfully")
        elif coverage.ocr_confidence < 0.70:
            warnings.append(f"Low OCR confidence: {coverage.ocr_confidence:.2f}")

    if require_face:
        if not coverage.face_detection_attempted:
            failures.append("Face detection was not attempted")
        elif not coverage.face_detection_completed:
            failures.append("Face detection did not complete successfully")
        elif coverage.face_confidence < 0.70:
            warnings.append(f"Low face detection confidence: {coverage.face_confidence:.2f}")

    return CoverageGateResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
    )


@dataclass(frozen=True)
class ModeRequirements:
    require_ocr: bool
    require_face: bool


MODE_REQUIREMENTS: Dict[str, ModeRequirements] = {
    "full_image_contain": ModeRequirements(require_ocr=False, require_face=False),
    "validated_crop": ModeRequirements(require_ocr=True, require_face=True),
    "text_protected_crop": ModeRequirements(require_ocr=True, require_face=False),
    "face_protected_crop": ModeRequirements(require_ocr=False, require_face=True),
    "manual_review": ModeRequirements(require_ocr=False, require_face=False),
}


def get_mode_requirements(mode: str) -> ModeRequirements:
    return MODE_REQUIREMENTS.get(mode, ModeRequirements(require_ocr=True, require_face=True))


@dataclass
class CropEvidence:
    boundary_score: float
    region_safety_score: float
    resolution_score: float
    overlap_score: float
    detector_coverage_score: float
    hard_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_hard_failure(self) -> bool:
        return bool(self.hard_failures)


def calculate_evidence_score(evidence: CropEvidence) -> float:
    if evidence.has_hard_failure:
        return 0.0
    if evidence.detector_coverage_score <= 0.0:
        return 0.0

    weights = {
        "boundary": 0.25,
        "region_safety": 0.30,
        "resolution": 0.15,
        "overlap": 0.15,
        "detector_coverage": 0.15,
    }

    score = (
        evidence.boundary_score * weights["boundary"]
        + evidence.region_safety_score * weights["region_safety"]
        + evidence.resolution_score * weights["resolution"]
        + evidence.overlap_score * weights["overlap"]
        + evidence.detector_coverage_score * weights["detector_coverage"]
    )
    return round(max(0.0, min(1.0, score)), 3)


def choose_rendering_decision(
    score: float,
    hard_failures: List[str],
    requires_manual_review: bool = False,
    minimum_score: float = 0.85,
) -> RenderDecision:
    if hard_failures:
        return "contain_safe"
    if requires_manual_review:
        return "contain_review"
    if score >= minimum_score:
        return "approved_crop"
    if score >= 0.65:
        return "contain_review"
    return "contain_safe"


@dataclass
class CropValidation:
    approved: bool
    decision: RenderDecision
    score: float
    hard_failures: List[str]
    soft_warnings: List[str]
    protected_results: List[RegionSafetyResult]
    crop_box: Box


def validate_crop_candidate(
    crop: Box,
    image_width: int,
    image_height: int,
    protected_regions: List[ProtectedRegion],
    coverage: DetectionCoverage,
    boundary_score: float = 0.90,
    neighboring_boxes: Optional[List[Box]] = None,
    mode: str = "validated_crop",
    min_width: int = 240,
    min_height: int = 240,
    min_area_ratio: float = 0.08,
) -> CropValidation:
    """
    Comprehensive validator combining geometry, neighbor collision, protected regions, and coverage gate.
    """
    hard_failures: List[str] = []
    soft_warnings: List[str] = []
    protected_results: List[RegionSafetyResult] = []

    x1, y1, x2, y2 = crop
    w = x2 - x1
    h = y2 - y1
    area = w * h
    img_area = max(1, image_width * image_height)

    # 1. Geometry checks
    if x1 < 0 or y1 < 0 or x2 > image_width or y2 > image_height:
        hard_failures.append("Crop exceeds image boundaries")
    if x2 <= x1 or y2 <= y1:
        hard_failures.append("Invalid crop coordinates")
    if w < min_width or h < min_height:
        hard_failures.append(f"Crop resolution is too small ({w}x{h} < {min_width}x{min_height})")
    if area / float(img_area) < min_area_ratio:
        soft_warnings.append("Crop occupies a small portion of source")

    # 2. Neighbor overlap checks
    overlap_score = 1.0
    if neighboring_boxes:
        for idx, neighbor in enumerate(neighboring_boxes):
            ov_area = intersection_area(crop, neighbor)
            if ov_area > 0:
                hard_failures.append(f"Crop overlaps neighboring box #{idx + 1}")
                overlap_score = 0.0

    # 3. Coverage Gate
    reqs = get_mode_requirements(mode)
    coverage_result = check_detection_coverage(
        coverage=coverage,
        require_ocr=reqs.require_ocr,
        require_face=reqs.require_face,
    )
    if not coverage_result.passed:
        hard_failures.extend(coverage_result.failures)
    soft_warnings.extend(coverage_result.warnings)

    detector_cov_score = coverage.quality_score(reqs.require_ocr, reqs.require_face)

    # 4. Protected regions check
    for reg in protected_regions:
        expanded_reg = expand_region(reg, image_width, image_height, margin_ratio=0.10)
        res = validate_protected_region(crop, expanded_reg)
        protected_results.append(res)
        if not res.safe:
            hard_failures.append(res.reason)

    if not protected_regions:
        # If no protected regions detected, we don't grant free 1.0 if detection was required
        region_safety_score = 1.0 if detector_cov_score > 0 else 0.5
    else:
        region_safety_score = sum(r.containment for r in protected_results) / float(len(protected_results))

    # Resolution score
    res_score = min(1.0, (w / float(image_width) + h / float(image_height)) / 1.5)

    evidence = CropEvidence(
        boundary_score=boundary_score,
        region_safety_score=region_safety_score,
        resolution_score=res_score,
        overlap_score=overlap_score,
        detector_coverage_score=detector_cov_score,
        hard_failures=hard_failures,
        warnings=soft_warnings,
    )

    score = calculate_evidence_score(evidence)
    decision = choose_rendering_decision(score, hard_failures)
    approved = (decision == "approved_crop")

    return CropValidation(
        approved=approved,
        decision=decision,
        score=score,
        hard_failures=hard_failures,
        soft_warnings=soft_warnings,
        protected_results=protected_results,
        crop_box=crop,
    )
