"""PT Home Exercise Analytical Tools: an MCP server with five tools.

Tools 1 to 3 come from Homework 4 (joint_angle, session_time, rom_projection).
Tools 4 and 5 are new and come from the requirements in our user research:
  4. set_check       -> Requirement 1: after each set, say whether it was in the
                        patient's own safe range and whether to continue, adjust or ask the PT.
  5. weekly_summary  -> Requirements 2 and 3: a weekly check-in summary for the PT,
                        including the questions the patient saved between visits.

Run:  python pt_tools_server.py            (stdio transport, for MCP clients)
Test: npx @modelcontextprotocol/inspector python pt_tools_server.py
Needs: pip install "mcp>=2"

These tools do arithmetic on numbers they are given. They do not diagnose,
and they do not decide whether pain is safe for a specific patient: the pain
limit is a setting the PT owns.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer(
    name="pt-home-exercise-tools",
    instructions=(
        "Analytical tools for home physical therapy exercise. Every number in an answer "
        "must come from a tool result. Tools give exercise analysis, not medical advice; "
        "when a result says to ask the PT, tell the user that plainly."
    ),
)

Deg = Annotated[float, Field(ge=0, le=180, description="Angle in degrees, 0 to 180 (180 = straight limb)")]
Pain = Annotated[int, Field(ge=0, le=10, description="Patient-rated pain, 0 (none) to 10 (worst imaginable)")]


# ---------------------------------------------------------------- Tool 1 (HW4)
class JointAngleResult(BaseModel):
    angle_deg: float = Field(description="Angle at joint B in degrees (180 = straight)")
    within_target: bool | None = Field(None, description="True if inside the target range; null if no target given")
    degrees_outside_target: float | None = Field(None, description="Degrees outside the target range (0 if inside)")
    target_range_deg: list[float] | None = None


@server.tool(title="Joint angle check")
def joint_angle(
    ax: Annotated[float, Field(description="Point A x (e.g. hip), same unit as the other points")],
    ay: Annotated[float, Field(description="Point A y")],
    bx: Annotated[float, Field(description="Joint B x (e.g. knee)")],
    by: Annotated[float, Field(description="Joint B y")],
    cx: Annotated[float, Field(description="Point C x (e.g. ankle)")],
    cy: Annotated[float, Field(description="Point C y")],
    target_min_deg: Deg | None = None,
    target_max_deg: Deg | None = None,
) -> JointAngleResult:
    """Angle at a joint from three 2D points (A, joint B, C), optionally checked against a
    PT target range. Assumes a side-on camera so the movement is in the image plane.
    Coordinates can be pixels or MediaPipe's 0 to 1 values, as long as all three use the same unit."""
    for v in (ax, ay, bx, by, cx, cy):
        if not math.isfinite(v):
            raise ToolError("All coordinates must be finite numbers.")
    bax, bay, bcx, bcy = ax - bx, ay - by, cx - bx, cy - by
    la, lc = math.hypot(bax, bay), math.hypot(bcx, bcy)
    if la == 0 or lc == 0:
        raise ToolError("Point A and point C must not be at the same place as joint B.")
    if target_min_deg is not None and target_max_deg is not None and target_min_deg > target_max_deg:
        raise ToolError("target_min_deg cannot be larger than target_max_deg.")
    cos = max(-1.0, min(1.0, (bax * bcx + bay * bcy) / (la * lc)))
    ang = math.degrees(math.acos(cos))
    out = JointAngleResult(angle_deg=round(ang, 1))
    if target_min_deg is not None or target_max_deg is not None:
        lo = target_min_deg if target_min_deg is not None else 0.0
        hi = target_max_deg if target_max_deg is not None else 180.0
        out.within_target = lo <= ang <= hi
        out.degrees_outside_target = round(max(lo - ang, ang - hi, 0), 1)
        out.target_range_deg = [lo, hi]
    return out


# ---------------------------------------------------------------- Tool 2 (HW4)
class SessionTimeResult(BaseModel):
    total_minutes: float
    time_under_tension_minutes: float = Field(description="Minutes spent actually moving")
    percent_time_moving: float
    fits_budget: bool | None = Field(None, description="Null if no time budget was given")
    max_sets_that_fit: int | None = Field(None, description="Most sets per exercise that fit the budget (0 = none)")


@server.tool(title="Session time planner")
def session_time(
    exercises: Annotated[int, Field(ge=1, le=12, description="Number of exercises, 1 to 12")],
    sets: Annotated[int, Field(ge=1, le=10, description="Sets per exercise, 1 to 10")],
    reps: Annotated[int, Field(ge=1, le=30, description="Reps per set, 1 to 30")],
    seconds_per_rep: Annotated[float, Field(ge=1, le=10, description="Tempo, seconds per rep, 1 to 10")],
    rest_between_sets_s: Annotated[float, Field(ge=0, le=300, description="Rest between sets, seconds, 0 to 300")],
    rest_between_exercises_s: Annotated[float, Field(ge=0, le=300, description="Rest between exercises, seconds, 0 to 300")] = 60,
    time_budget_min: Annotated[float | None, Field(ge=1, le=120, description="Time available, minutes, 1 to 120")] = None,
) -> SessionTimeResult:
    """Total minutes for a home exercise session, the share spent moving, and (if a time budget
    is given) whether it fits and how many sets per exercise would fit. Assumes every exercise
    uses the same sets, reps and tempo, with no setup time beyond the rests."""

    def total_s(n_sets: int) -> float:
        per_exercise = n_sets * reps * seconds_per_rep + (n_sets - 1) * rest_between_sets_s
        return exercises * per_exercise + (exercises - 1) * rest_between_exercises_s

    t = total_s(sets)
    tut = exercises * sets * reps * seconds_per_rep
    out = SessionTimeResult(total_minutes=round(t / 60, 1), time_under_tension_minutes=round(tut / 60, 1),
                            percent_time_moving=round(100 * tut / t, 0))
    if time_budget_min is not None:
        out.fits_budget = t <= time_budget_min * 60
        fitting = [s for s in range(1, 11) if total_s(s) <= time_budget_min * 60]
        out.max_sets_that_fit = max(fitting) if fitting else 0
    return out


# ---------------------------------------------------------------- Tool 3 (HW4)
class RomProjectionResult(BaseModel):
    gain_deg_per_week: float
    status: str
    days_to_target: int | None = None
    weeks_to_target: float | None = None
    warning: str | None = None


@server.tool(title="Range-of-motion recovery projection")
def rom_projection(
    earlier_deg: Deg,
    current_deg: Deg,
    days_between: Annotated[float, Field(ge=1, le=180, description="Days between the two measurements, 1 to 180")],
    target_deg: Deg,
) -> RomProjectionResult:
    """Days and weeks until a range-of-motion target is reached, from two past measurements,
    assuming a constant (linear) rate. Larger angle = more motion (e.g. knee flexion).
    Warns beyond 12 weeks and refuses to project when progress has stalled."""
    rate = (current_deg - earlier_deg) / days_between
    gain = round(rate * 7, 1)
    if current_deg >= target_deg:
        return RomProjectionResult(gain_deg_per_week=gain, status="Target already reached.")
    if rate <= 0:
        return RomProjectionResult(gain_deg_per_week=gain,
                                   status="No progress between measurements, so no projection is possible. Discuss with the PT.")
    days = (target_deg - current_deg) / rate
    out = RomProjectionResult(gain_deg_per_week=gain, days_to_target=round(days), weeks_to_target=round(days / 7, 1),
                              status="Projected with a constant rate of progress.")
    if days > 84:
        out.warning = "Projection is beyond 12 weeks; real recovery usually slows down, so treat this as optimistic."
    return out


# ---------------------------------------------------------------- Tool 4 (new)
class SetCheckResult(BaseModel):
    reps: int
    reps_in_range: int
    percent_in_range: float
    mean_angle_deg: float
    rep_to_rep_spread_deg: float = Field(description="Standard deviation of the rep angles (0 if one rep)")
    pain_zone: Literal["safe", "acceptable", "above_limit"] = Field(
        description="safe: 0 to 2; acceptable: above 2 up to the PT's limit; above_limit: over the limit")
    next_step: Literal["continue", "adjust_form", "stop_and_ask_pt"]
    reasons: list[str]
    message: str = Field(description="Calm, plain-language message for the patient")


@server.tool(title="Per-set check")
def set_check(
    rep_angles_deg: Annotated[list[Deg], Field(min_length=1, max_length=50,
        description="Key joint angle reached in each rep of the set, degrees (e.g. knee angle at the bottom of a squat)")],
    target_min_deg: Deg,
    target_max_deg: Deg,
    pain_during_set: Pain,
    pain_limit: Annotated[int, Field(ge=0, le=10,
        description="Highest acceptable pain during exercise, set by the PT. Default 5 (pain monitoring model)")] = 5,
    min_percent_in_range: Annotated[float, Field(ge=0, le=100,
        description="Share of reps that must be in range to count as good form, percent. Default 80")] = 80,
) -> SetCheckResult:
    """After one set, compare each rep with the patient's own target range from their PT, place
    the patient's pain rating in a zone, and return one next step: continue, adjust form, or stop
    and ask the PT. Pain zones follow the pain monitoring model (Thomee 1997: 0 to 2 safe, up to 5
    acceptable); the PT can change the limit. Pain always outranks form."""
    if target_min_deg > target_max_deg:
        raise ToolError("target_min_deg cannot be larger than target_max_deg.")
    if pain_limit < 2:
        raise ToolError("pain_limit must be at least 2, because 0 to 2 is the 'safe' zone.")
    n = len(rep_angles_deg)
    inside = [target_min_deg <= a <= target_max_deg for a in rep_angles_deg]
    k = sum(inside)
    pct = round(100 * k / n, 0)
    spread = round(statistics.pstdev(rep_angles_deg), 1) if n > 1 else 0.0
    zone = "safe" if pain_during_set <= 2 else ("acceptable" if pain_during_set <= pain_limit else "above_limit")

    reasons: list[str] = []
    if zone == "above_limit":
        step = "stop_and_ask_pt"
        reasons.append(f"Pain {pain_during_set}/10 is above your PT's limit of {pain_limit}/10.")
        msg = (f"Let's stop here for today. Pain of {pain_during_set} out of 10 is above the level your PT set. "
               "Rest, and send your PT a note about it. If the pain is severe or sudden, call your clinic.")
    elif pct < min_percent_in_range:
        step = "adjust_form"
        short = [i + 1 for i, ok in enumerate(inside) if not ok]
        reasons.append(f"{n - k} of {n} reps were outside {target_min_deg:g} to {target_max_deg:g} degrees (reps {short}).")
        msg = (f"Good effort. {k} of {n} reps reached your target. Slow down and aim for the range your PT showed you. "
               "If it keeps happening, save a question for your PT.")
    else:
        step = "continue"
        reasons.append(f"{k} of {n} reps in range; pain {pain_during_set}/10 is within your PT's limit.")
        msg = ("Nice, steady set. That was in your range. Keep going at this pace." if k == n else
               f"Nice, steady set. {k} of {n} reps were in your range, which is enough. Keep going at this pace.")
    if zone == "acceptable":
        reasons.append("Some pain is expected; it should settle by the next morning. If it doesn't, tell your PT.")
    if spread > 10:
        reasons.append(f"Reps varied a lot (spread {spread} degrees); fatigue may be setting in.")

    return SetCheckResult(reps=n, reps_in_range=k, percent_in_range=pct,
                          mean_angle_deg=round(statistics.fmean(rep_angles_deg), 1),
                          rep_to_rep_spread_deg=spread, pain_zone=zone, next_step=step,
                          reasons=reasons, message=msg)


# ---------------------------------------------------------------- Tool 5 (new)
class Session(BaseModel):
    day: Annotated[date, Field(description="Session date, YYYY-MM-DD, within the week")]
    sets_done: Annotated[int, Field(ge=0, le=50)]
    sets_prescribed: Annotated[int, Field(ge=1, le=50)]
    max_pain: Pain | None = Field(None, description="Highest pain during the session, 0 to 10")
    next_morning_pain: Pain | None = Field(None, description="Pain the morning after, 0 to 10")


class WeeklySummaryResult(BaseModel):
    week: str
    sessions_done: int
    sessions_prescribed: int
    session_adherence_percent: float
    set_completion_percent: float
    longest_gap_days: int = Field(description="Longest run of days in the week with no session")
    days_pain_above_limit: list[str]
    days_pain_not_settling: list[str] = Field(description="Days where next-morning pain was higher than pain during the session")
    patient_questions: list[str]
    flags: list[str]
    summary_for_pt: str


@server.tool(title="Weekly check-in summary for the PT")
def weekly_summary(
    week_start: Annotated[date, Field(description="First day of the 7-day week, YYYY-MM-DD")],
    sessions: Annotated[list[Session], Field(max_length=28, description="Sessions done this week (an empty list means none)")],
    prescribed_sessions_per_week: Annotated[int, Field(ge=1, le=14)],
    patient_questions: Annotated[list[Annotated[str, Field(min_length=1, max_length=500)]],
                                 Field(max_length=20, description="Questions the patient saved between visits")] = [],
    pain_limit: Annotated[int, Field(ge=2, le=10, description="PT's pain limit, 0 to 10. Default 5")] = 5,
) -> WeeklySummaryResult:
    """Summarize one week of home exercise for the PT: sessions done vs prescribed, sets completed,
    the longest gap without exercise, days when pain went above the PT's limit or did not settle
    by the next morning, and the questions the patient saved. Reports facts and flags only;
    it does not grade the patient."""
    week_end = week_start + timedelta(days=6)
    for s in sessions:
        if not week_start <= s.day <= week_end:
            raise ToolError(f"Session date {s.day} is outside the week {week_start} to {week_end}.")
        if s.sets_done > s.sets_prescribed * 2:
            raise ToolError(f"sets_done ({s.sets_done}) on {s.day} is more than twice sets_prescribed; check the entry.")

    days_with = sorted({s.day for s in sessions})
    n_done = len(sessions)
    adherence = round(100 * min(n_done, prescribed_sessions_per_week) / prescribed_sessions_per_week, 0)
    presc = sum(s.sets_prescribed for s in sessions)
    completion = round(100 * sum(min(s.sets_done, s.sets_prescribed) for s in sessions) / presc, 0) if presc else 0.0

    gap, run = 0, 0
    for i in range(7):
        if week_start + timedelta(days=i) in days_with:
            run = 0
        else:
            run += 1
            gap = max(gap, run)

    over = sorted({s.day.isoformat() for s in sessions if s.max_pain is not None and s.max_pain > pain_limit})
    not_settling = sorted({s.day.isoformat() for s in sessions
                           if s.max_pain is not None and s.next_morning_pain is not None
                           and s.next_morning_pain > s.max_pain})
    flags = []
    if gap >= 3:
        flags.append(f"{gap} days in a row with no session.")
    if adherence < 50:
        flags.append(f"Fewer than half of prescribed sessions done ({n_done} of {prescribed_sessions_per_week}).")
    if over:
        flags.append(f"Pain above the limit of {pain_limit}/10 on {', '.join(over)}.")
    if not_settling:
        flags.append(f"Pain was higher the next morning on {', '.join(not_settling)}.")
    if patient_questions:
        flags.append(f"{len(patient_questions)} question(s) from the patient to answer.")

    summary = (f"Week of {week_start}: {n_done} of {prescribed_sessions_per_week} sessions, "
               f"{completion:g}% of prescribed sets in those sessions, longest gap {gap} days. "
               + (" ".join(flags) if flags else "No flags."))
    return WeeklySummaryResult(week=f"{week_start} to {week_end}", sessions_done=n_done,
                               sessions_prescribed=prescribed_sessions_per_week,
                               session_adherence_percent=adherence, set_completion_percent=completion,
                               longest_gap_days=gap, days_pain_above_limit=over,
                               days_pain_not_settling=not_settling, patient_questions=list(patient_questions),
                               flags=flags, summary_for_pt=summary)


if __name__ == "__main__":
    server.run()  # stdio transport
