# URPP 14D-4B4D2A — Source-Verified Equation Records v0.1

## 1. Purpose and status

Purpose: establish an independently checked mathematical reference for
evaluating the local Professor's answers about equations (7), (10), (15),
and (16).

Status: SOURCE IMAGE REVIEW COMPLETED BY ASSISTANT.
Final project-owner sign-off and evaluator implementation remain pending.

This document records mathematical relationships and source locations.
It is not a claim that URPP can already verify arbitrary mathematical
answers automatically.

The source PDF is not copied into this repository.

## 2. Source identity

Paper:
Sungsoo Ha and Klaus Mueller,
"A Look-Up Table-Based Ray Integration Framework for 2-D/3-D
Forward and Back Projection in X-Ray CT,"
IEEE Transactions on Medical Imaging, 37(2), 2018.

Local source filename:
URPP_CT_LTRI_2018_part1_pages_1-6.pdf

Original six-page PDF SHA-256:
20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f

Existing URPP Course Pack SHA-256:
fbf19109e86539e119afe8cee3acd3e9a8d812e2c334217c911263ba56dbeeb2

These are different objects:
- PDF SHA identifies the original six-page file.
- Course Pack SHA identifies URPP's derived, version-pinned material package.

Source pages inspected:
- PDF page 4: equation (7).
- PDF page 5: equation (10).
- PDF page 6: equations (15) and (16).

The paper's printed page numbers are 364, 365, and 366,
respectively.

The source is subject to its existing licensed-use restrictions.
The project must not publish the original PDF or substantial
copyrighted passages merely to create an evaluation dataset.

## 3. Equation (7): cone-beam volume integration

PDF page: 4.
URPP source: excerpt-4.

Mathematical structure:

p_i^theta ≈
    [1 / (|sin(alpha_i)| gamma_(phi,i) gamma_(varphi,i))]
    *
    sum_(n in Omega_SBP)
    [
        f[n] d_n / ||v_n - v_src||^2
    ]

Required relationships:

1. The three angular factors occur in the denominator of
   the external normalization factor.

2. The sum is over voxels intersecting the source-bin pyramid,
   denoted Omega_SBP.

3. d_n denotes ray-voxel intersection volume.

4. f[n] is the value associated with voxel n.

5. The squared distance appears in the denominator of each
   voxel contribution.

6. The source position and voxel-center position must not
   be silently exchanged for unrelated geometric quantities.

7. The expression is an approximation in the paper.

Critical failures:

- Moving either gamma factor into the numerator.
- Removing the intersection-volume weight.
- Describing the expression as an unweighted sum of voxel values.
- Replacing the squared distance with a linear distance.
- Claiming the paper's main text contains the full derivation
  when it directs readers to supplementary material.

## 4. Equation (10): height from a plane-specific volume

PDF page: 5.
URPP source: excerpt-5.

Mathematical structure:

h_(PL_s,top) =
    V_(PL_s,top) / (Delta_x * Delta_y)

Required relationships:

1. The formula refers to the top plane's corresponding volume.

2. An analogous height is calculated for the bottom plane.

3. The difference between the two plane-derived heights
   determines the effective height h_eff.

4. The approximate intersection volume is then obtained using:

   V_overlap ≈ S_base * h_eff

Critical failures:

- Treating equation (10) as the final complete
  ray-voxel intersection-volume formula.
- Omitting the role of the two planes when explaining h_eff.
- Confusing the voxel base Delta_x * Delta_y with S_base.

## 5. Equation (15): Regression Method

PDF page: 6.
URPP source: excerpt-6.

The paper labels this approach Regression Method.

Mathematical structure:

height =
    Delta_z / 2 - D_pl,
        if 0 <= D_pl <= Delta_z / 2

    0,
        otherwise

The text introducing the approximation specifies the simplified
case theta_varphi = theta_phi = 0.

Required relationships:

1. This is an approximation, not the exact general hLUT.

2. The nonzero branch subtracts D_pl from Delta_z / 2.

3. The interval condition and zero branch must both be preserved.

4. The method must not be renamed Distance Method.

Critical failures:

- Reversing the subtraction.
- Dropping the branch condition.
- Confusing this equation with the interval-overlap formula (16).
- Presenting its simplified angular setting as a general proof
  for all orientations.

## 6. Equation (16): Distance Method

PDF page: 6.
URPP source: excerpt-6.

The paper labels this approach Distance Method.

Mathematical structure:

h_eff =
    min(z_plus, t_c_plus) - max(z_minus, t_c_minus),
        if overlap

    0,
        otherwise

Required relationships:

1. The calculation concerns overlap along the common z-axis
   passing through the voxel center.

2. z_plus and z_minus are the voxel's upper and lower endpoints
   on that axis.

3. t_c_plus and t_c_minus are projected detector-bin endpoints
   on the same axis.

4. The upper limit is selected using min().
   The lower limit is selected using max().

5. The non-overlap branch returns zero.

Critical failures:

- Reversing min and max.
- Treating the projected t_c endpoints as unprojected
  detector coordinates.
- Returning a negative effective height for non-overlap.
- Calling equation (16) Regression Method.

## 7. Evaluation boundaries

L1 — Engineering validity:

- Valid structured model response.
- Valid answer status and selected Source IDs.
- Existing permission and source-version boundaries preserved.
- Bounded generation retry.
- No unintended Session or Student State writes.

L2 — Mathematical fidelity:

- The answer actually addresses the student's current request.
- Requested equations are provided, rather than replaced
  with unrelated summaries.
- Mathematical relationships agree with the verified PDF.
- Variables, conditions, and method names are preserved.
- Missing evidence is acknowledged instead of fabricated.

L1 PASS does not imply L2 PASS.

An evaluator must not mark an answer correct merely because it
contains a recognized equation number, an authorized Source ID,
or a few expected mathematical symbols.

Equivalent mathematical notation may be acceptable, provided
the mathematical relationships and conditions are unchanged.

## 8. Known project observations

Previous local Professor runs produced:

A. An equation (7) response with angular gamma factors
   incorrectly moved into the numerator.

B. An equation (7) explanation that lost the meaning of
   the weighted volume contribution.

C. An equation (15)/(16) response that passed the output
   contract after JSON regeneration, but did not provide
   the two complete equations requested by the student.

These are observed failures for the tested inputs and model
configuration, not a measured overall mathematical error rate.

## 9. New hypothesis: text extraction and formula fidelity

H-MATH-EXTRACTION-01:

Loss of mathematical layout during PDF text extraction may
contribute to formula-copying errors in the local Professor.

Motivation:

The original PDF visually contains properly typeset fractions,
indices, and piecewise expressions.

The existing URPP Course Pack contains extracted text in which
several of those structures are separated across lines.

This observation does not prove that extraction caused any
specific incorrect model output.

Proposed comparison:

Condition A:
Existing extracted-text Source Excerpts.

Condition B:
The same Source Excerpts supplemented with an independently
checked, version-bound EquationRecord for the requested equation.

Keep fixed:
- Student question.
- Source PDF version.
- Model tag and generation settings.
- Existing response and citation contracts.

Measure separately:
- Formula structural correctness.
- Variable and method attribution.
- Answer omission.
- Invalid-output or refusal frequency.
- Generation cost and latency.

Do not give either condition access to the evaluation rubric
as a hidden answer key.

## 10. Next implementation boundary

The next task is a read-only evaluation harness.

It may:
- Run frozen questions against the existing local Professor.
- Collect generation metadata and response text in an
  explicitly private evaluation workspace.
- Link each case to this source-verified record.
- Report L1 results independently from L2 review.
- Preserve failures and abstentions.

It must not:
- Modify the original course PDF or Course Pack.
- Rewrite model-generated formulas to make them pass.
- Automatically label mathematical content as human-verified.
- Write evaluation turns into the original student Session.
- Modify Evidence Eligibility, Mastery, or Student State.
- Change the Professor prompt or Source Selector
  as a side effect of building the evaluator.

This record is an evaluation reference, not a runtime teaching
permission or an automatically approved source of new
student-learning evidence.
