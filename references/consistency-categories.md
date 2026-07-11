# UI/UX Consistency Categories

This document defines all 23 consistency categories that the audit checks.

## Part 1: UI/UX Consistency Checks

### 1. Visual Identity Consistency
**What to check:** Same semantic role = same styling (color, border-radius, shadow, padding, font-weight, size)
**Layer:** Browser-level (computed styles) + Source-level (CSS extraction)
**Severity:** Medium

### 2. Spacing Rhythm
**What to check:** Spacing follows a defined grid (4px/8px increments); flag arbitrary values
**Layer:** Browser-level + Source-level (CSS analysis)
**Severity:** Medium

### 3. Typography Scale
**What to check:** Font sizes/weights from a small fixed scale; flag one-off sizes
**Layer:** Browser-level + Source-level (CSS analysis)
**Severity:** Medium

### 4. Icon Set Consistency
**What to check:** Same icon library, stroke width, and optical size throughout
**Layer:** Browser-level (DOM inspection) + Source-level (import analysis)
**Severity:** Medium

### 5. Interaction State Consistency
**What to check:** Hover, focus, active, disabled states identical for same component type
**Layer:** Browser-level (computed styles for pseudo-states)
**Severity:** Low

### 6. Modal/Popup/Overlay Behavior
**What to check:** Identical animation, backdrop, close behavior across all modals
**Layer:** Browser-level (DOM + interaction testing)
**Severity:** Medium

### 7. Loading/Empty/Error State Consistency
**What to check:** Every data view has consistent skeleton, empty, and error states
**Layer:** Browser-level (DOM inspection) + Source-level (component analysis)
**Severity:** Medium

### 8. Form Validation Consistency
**What to check:** Inline vs. toast errors, timing, error styling consistent across forms
**Layer:** Browser-level (DOM inspection)
**Severity:** Medium

### 9. Content/Microcopy Consistency
**What to check:** Button casing, date/time/number formatting, message tone consistent
**Layer:** Browser-level (text extraction)
**Severity:** Low

### 10. Structural/Navigational Consistency
**What to check:** Breadcrumbs, back-button, primary action placement consistent
**Layer:** Browser-level (DOM structure)
**Severity:** Low

### 11. Responsive/Cross-Breakpoint Consistency
**What to check:** Same component behaves consistently across breakpoints
**Layer:** Browser-level (viewport testing)
**Severity:** Medium

### 12. Accessibility as Consistency Signal
**What to check:** Automated a11y checks; inconsistent a11y = inconsistency bug
**Layer:** Browser-level (DOM inspection + axe-core)
**Severity:** High

### 13. Motion/Animation Consistency
**What to check:** Transition durations/easing from a small fixed set
**Layer:** Browser-level + Source-level (CSS analysis)
**Severity:** Low

### 14. Layout Integrity Bugs
**What to check:** Overflow, z-index stacking, CLS issues
**Layer:** Browser-level (layout inspection)
**Severity:** High

### 15. Data Density/Truncation Consistency
**What to check:** Text truncation, row/card heights behave consistently
**Layer:** Browser-level (computed styles)
**Severity:** Low

### 16. Iconography/Color Semantics
**What to check:** Same icon = same action; color meanings consistent
**Layer:** Browser-level (DOM + style analysis)
**Severity:** Medium

### 17. Empty/Zero/Singular-Plural Correctness
**What to check:** "0 items" vs "No items" vs blank; grammar bugs
**Layer:** Browser-level (text extraction)
**Severity:** Low

### 18. Pagination/Infinite-Scroll Consistency
**What to check:** Same pattern for similar list types
**Layer:** Browser-level (DOM inspection)
**Severity:** Medium

### 19. Notification/Toast Consistency
**What to check:** Position, duration, dismiss, stacking behavior consistent
**Layer:** Browser-level (DOM inspection)
**Severity:** Low

### 20. Permission/Role-Based UI Consistency
**What to check:** Disabled/hidden features behave identically per role
**Layer:** Browser-level (DOM inspection)
**Severity:** Medium

### 21. Theming Consistency (Dark Mode)
**What to check:** Every component has a deliberate themed counterpart
**Layer:** Browser-level + Source-level (CSS analysis)
**Severity:** Low

### 22. Input Affordance Consistency
**What to check:** Consistent border/focus/error visual language for inputs
**Layer:** Browser-level (computed styles)
**Severity:** Low

### 23. Print/Export/PDF View Consistency
**What to check:** Exported views align with app design language
**Layer:** Source-level (CSS @media print analysis)
**Severity:** Low
