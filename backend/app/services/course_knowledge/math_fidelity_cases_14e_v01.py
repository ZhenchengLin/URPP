"""URPP 14E — Frozen math-fidelity benchmark cases v0.2. Gold source: docs/URPP_14D-4B4D2A_source_verified_equations_v01.md (source-image review by assistant; project-owner sign-off pending). v0.1 cases were frozen before any candidate output was viewed. v0.2 (2026-10-06, owner request) translates the questions to English; gold, scope, and expected outcomes are unchanged. v0.1 and v0.2 results are not directly comparable."""

from app.services.course_knowledge.models_v01 import CourseSourceRefV01
from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    SourceGroundedBenchmarkCaseV01, BenchmarkGoldV01,
    BenchmarkEquationGoldV01, BenchmarkEvidenceExpectationV01,
    BenchmarkConversationTurnV01, benchmark_case_digest_v01,
)

BENCHMARK_VERSION_14E_V01 = "14e-math-fidelity-v0.2"
PINNED_PACK_SHA256_14E_V01 = "fbf19109e86539e119afe8cee3acd3e9a8d812e2c334217c911263ba56dbeeb2"
OBJECTIVE_ID_14E_V01 = "uploaded-material"
GOLD_REVIEW_STATUS_14E_V01 = "assistant_source_image_review_owner_signoff_pending"

_EXCERPT_4 = CourseSourceRefV01(
    source_id='local-pdf-20654a6a6f607efe7d51fde5-excerpt-4',
    source_revision='20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f',
    source_locator='local-pdf://URPP_CT_LTRI_2018_part1_pages_1-6.pdf?sha256=20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f&pages=4-4&excerpt=4',
    content_sha256='a889438d7dcb774044aa5a885f6e7f66596ef0409d2d45a5578a50ac49f88674',
)
_EXCERPT_5 = CourseSourceRefV01(
    source_id='local-pdf-20654a6a6f607efe7d51fde5-excerpt-5',
    source_revision='20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f',
    source_locator='local-pdf://URPP_CT_LTRI_2018_part1_pages_1-6.pdf?sha256=20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f&pages=5-5&excerpt=5',
    content_sha256='aaba2eac18c5c135a0e4eadf3d24debc430860587588b7b77fe5665035d560e2',
)
_EXCERPT_6 = CourseSourceRefV01(
    source_id='local-pdf-20654a6a6f607efe7d51fde5-excerpt-6',
    source_revision='20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f',
    source_locator='local-pdf://URPP_CT_LTRI_2018_part1_pages_1-6.pdf?sha256=20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f&pages=6-6&excerpt=6',
    content_sha256='cefc728d7401d46fb05d596c42b97bd4e841982b5b116857229f219f706c4aad',
)

_EQ7 = r"p_i^{\theta} \approx \frac{1}{\lvert \sin\alpha_i \rvert \, \gamma_{\phi,i} \, \gamma_{\varphi,i}} \sum_{n \in \Omega_{SBP}} \frac{f[n] \, d_n}{\lVert v_n - v_{src} \rVert^{2}}"
_EQ10 = r"h_{PL_s,\mathrm{top}} = \frac{V_{PL_s,\mathrm{top}}}{\Delta x \, \Delta y}"
_EQ15 = r"\mathrm{height} = \begin{cases} \frac{\Delta z}{2} - D_{pl}, & 0 \le D_{pl} \le \frac{\Delta z}{2} \\ 0, & \text{otherwise} \end{cases}"
_EQ16 = r"h_{\mathrm{eff}} = \begin{cases} \min(z^{+}, t_c^{+}) - \max(z^{-}, t_c^{-}), & \text{if overlap} \\ 0, & \text{otherwise} \end{cases}"
_NOTES = "gold: " + GOLD_REVIEW_STATUS_14E_V01 + "; protocol: URPP_14D-4B4D2 §3"

MATH_FIDELITY_CASE_IDS_14E_V01 = (
    "14e-M07-COPY","14e-M07-EXPLAIN","14e-M10-COPY","14e-M15-COPY",
    "14e-M16-COPY","14e-M15-M16","14e-M07-MISSING","14e-M07-FOLLOW",
)

def _ev(ref, locator, rationale, kind="equation"):
    return BenchmarkEvidenceExpectationV01(
        source_ref=ref, evidence_locator=locator,
        evidence_kind=kind, rationale=rationale,
    )

def _eq(label, latex):
    return BenchmarkEquationGoldV01(
        equation_label=label, normalized_latex=latex,
    )

def _case(case_id, qtype, question, scope, evidence, facts, equations,
          errors, categories, outcome="answer", language="en", prior=()):
    return SourceGroundedBenchmarkCaseV01(
        case_id=case_id, benchmark_version=BENCHMARK_VERSION_14E_V01,
        split="development", language=language, question_type=qtype,
        question=question, prior_turns=prior, source_scope_refs=scope,
        required_evidence=evidence,
        gold=BenchmarkGoldV01(
            required_facts=facts, equations=equations,
            prohibited_errors=errors, acceptable_variants=(),
        ),
        expected_outcome=outcome, evaluation_categories=categories,
        notes=_NOTES,
    )

def build_math_fidelity_cases_14e_v01() -> tuple[SourceGroundedBenchmarkCaseV01, ...]:
    return (
        _case("14e-M07-COPY","equation_transcription",
            "Write out the paper's Equation (7) in full, keeping every multiplication and division in place and the summation sign.",(_EXCERPT_4,),
            (_ev(_EXCERPT_4,"PDF page 4, equation (7)","Frozen equation (7) source."),),
            ("The three angular factors |sin alpha_i|, gamma_(phi,i), gamma_(varphi,i) are in the denominator of the external normalization factor.",
             "The sum runs over n in Omega_SBP.",
             "Each voxel contribution is f[n] d_n divided by the squared distance ||v_n - v_src||^2.",
             "The expression is an approximation."),
            (_eq("7",_EQ7),),
            ("Moving either gamma factor into the numerator.",
             "Removing the intersection-volume weight d_n.",
             "Replacing the squared distance with a linear distance.",
             "Omitting the requested equation."),
            ("source_selection","formula_structure","formula_transcription","answer_omission")),
        _case("14e-M07-EXPLAIN","relationship",
            "Explain where the intersection volume, the squared distance, and the angular normalization each appear in Equation (7).",(_EXCERPT_4,),
            (_ev(_EXCERPT_4,"PDF page 4, equation (7)","Frozen equation (7) source."),),
            ("d_n is the ray-voxel intersection volume and weights each voxel value f[n].",
             "The squared distance ||v_n - v_src||^2 is in the denominator of each voxel contribution.",
             "The angular normalization factors are in the denominator of the external factor."),
            (_eq("7",_EQ7),),
            ("Describing the expression as an unweighted sum of voxel values.",
             "Moving either gamma factor into the numerator.",
             "Claiming the main text contains the full derivation."),
            ("formula_structure","variable_definition","unsupported_claim")),
        _case("14e-M10-COPY","multi_step",
            "Write out Equation (10), and explain how the two plane heights give h_eff.",(_EXCERPT_5,),
            (_ev(_EXCERPT_5,"PDF page 5, equation (10)","Frozen equation (10) source."),),
            ("Equation (10) computes the top-plane height from the top-plane volume divided by Delta x Delta y.",
             "An analogous height is computed for the bottom plane.",
             "The difference of the two plane heights gives h_eff.",
             "The approximate overlap volume is V_overlap ≈ S_base h_eff."),
            (_eq("10",_EQ10),),
            ("Treating equation (10) as the final exact intersection-volume formula.",
             "Omitting the role of the two planes.",
             "Confusing Delta x Delta y with S_base."),
            ("formula_transcription","formula_structure","applicability_condition","answer_omission")),
        _case("14e-M15-COPY","equation_transcription",
            "Write out the complete piecewise Equation (15), including its threshold and the name of the method.",(_EXCERPT_6,),
            (_ev(_EXCERPT_6,"PDF page 6, equation (15)","Frozen equation (15) source."),),
            ("Equation (15) is labelled Regression Method.",
             "The nonzero branch is Delta z / 2 minus D_pl when 0 <= D_pl <= Delta z / 2.",
             "Otherwise the height is 0.",
             "It is an approximation stated for the simplified case theta_varphi = theta_phi = 0."),
            (_eq("15",_EQ15),),
            ("Reversing the subtraction.","Dropping the branch condition or the zero branch.",
             "Calling it Distance Method.","Presenting the simplified angular setting as general."),
            ("formula_transcription","formula_structure","method_attribution","applicability_condition")),
        _case("14e-M16-COPY","equation_transcription",
            "Write out the complete piecewise Equation (16), the meaning of each variable, and the no-overlap branch.",(_EXCERPT_6,),
            (_ev(_EXCERPT_6,"PDF page 6, equation (16)","Frozen equation (16) source."),),
            ("Equation (16) is labelled Distance Method.",
             "z_plus and z_minus are the voxel's upper and lower endpoints on the common z-axis through the voxel center.",
             "t_c_plus and t_c_minus are projected detector-bin endpoints on the same axis.",
             "The upper limit uses min and the lower limit uses max.",
             "The non-overlap branch is 0."),
            (_eq("16",_EQ16),),
            ("Reversing min and max.","Treating t_c endpoints as unprojected detector coordinates.",
             "Returning a negative height for non-overlap.","Calling it Regression Method."),
            ("formula_transcription","formula_structure","variable_definition","method_attribution")),
        _case("14e-M15-M16","method_attribution",
            "Which method is each of Equations (15) and (16)? Write out both complete equations.",(_EXCERPT_6,),
            (_ev(_EXCERPT_6,"PDF page 6, equation (15)","Frozen equation (15) source."),
             _ev(_EXCERPT_6,"PDF page 6, equation (16)","Frozen equation (16) source.")),
            ("Equation (15) is Regression Method.","Equation (16) is Distance Method.",
             "Both complete piecewise equations are provided."),
            (_eq("15",_EQ15),_eq("16",_EQ16)),
            ("Swapping the two method names.","Replacing either equation with a prose summary."),
            ("method_attribution","formula_transcription","answer_omission")),
        _case("14e-M07-MISSING","unsupported","Write out the paper's Equation (7) in full.",(_EXCERPT_5,),(),(),(),
            ("Fabricating equation (7).","Citing excerpt-5 as the source of equation (7).",
             "Presenting another equation as equation (7)."),
            ("insufficient_evidence_handling","unsupported_claim","citation_attribution"),
            outcome="abstain"),
        _case("14e-M07-FOLLOW","follow_up","Send me the function",(_EXCERPT_4,_EXCERPT_5),
            (_ev(_EXCERPT_4,"PDF page 4, equation (7)","Representative provided-source context.","context"),),
            ("The answer states that the provided sources do not cover every equation in the paper, asks which equations are wanted, or gives representative equations only from the provided sources.",),
            (),("Claiming that all equations of the paper have been shown.",
                "Presenting equations from outside the provided sources."),
            ("conversation_context","insufficient_evidence_handling","instruction_following"),
            language="en",
            prior=(BenchmarkConversationTurnV01(role="student",text="What math equations are in the paper?"),)),
    )

def math_fidelity_case_digests_14e_v01() -> dict[str, str]:
    return {c.case_id: benchmark_case_digest_v01(c)
            for c in build_math_fidelity_cases_14e_v01()}
