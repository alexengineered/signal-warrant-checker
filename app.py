import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from io import BytesIO
from datetime import datetime

# PDF generation imports
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# =============================================================================
# MUTCD 2009 THRESHOLD DATA
# =============================================================================

# Warrant 1: Table 4C-1
WARRANT1_THRESHOLDS = {
    'condition_a': {
        (1, 1): {'100': (500, 150), '80': (400, 120), '70': (350, 105), '56': (280, 84)},
        (2, 1): {'100': (600, 150), '80': (480, 120), '70': (420, 105), '56': (336, 84)},
        (2, 2): {'100': (600, 200), '80': (480, 160), '70': (420, 140), '56': (336, 112)},
        (1, 2): {'100': (500, 200), '80': (400, 160), '70': (350, 140), '56': (280, 112)},
    },
    'condition_b': {
        (1, 1): {'100': (750, 75), '80': (600, 60), '70': (525, 53), '56': (420, 42)},
        (2, 1): {'100': (900, 75), '80': (720, 60), '70': (630, 53), '56': (504, 42)},
        (2, 2): {'100': (900, 100), '80': (720, 80), '70': (630, 70), '56': (504, 56)},
        (1, 2): {'100': (750, 100), '80': (600, 80), '70': (525, 70), '56': (420, 56)},
    }
}

# Warrant 2: Figure 4C-1 / 4C-2 curve points (major_vph, minor_vph threshold)
WARRANT2_CURVES = {
    '100': {
        (1, 1): [(300, 115), (400, 100), (500, 90), (600, 80), (700, 70), (800, 60), (900, 50), (1000, 40)],
        (2, 1): [(400, 115), (500, 100), (600, 90), (700, 80), (800, 70), (900, 60), (1000, 50), (1100, 40)],
        (2, 2): [(400, 150), (500, 135), (600, 120), (700, 105), (800, 95), (900, 85), (1000, 75), (1100, 65)],
        (1, 2): [(300, 150), (400, 135), (500, 120), (600, 105), (700, 95), (800, 85), (900, 75), (1000, 65)],
    },
    '70': {
        (1, 1): [(210, 80), (280, 70), (350, 63), (420, 56), (490, 49), (560, 42), (630, 35), (700, 28)],
        (2, 1): [(280, 80), (350, 70), (420, 63), (490, 56), (560, 49), (630, 42), (700, 35), (770, 28)],
        (2, 2): [(280, 105), (350, 95), (420, 84), (490, 74), (560, 67), (630, 60), (700, 53), (770, 46)],
        (1, 2): [(210, 105), (280, 95), (350, 84), (420, 74), (490, 67), (560, 60), (630, 53), (700, 46)],
    }
}

# Warrant 3: Figure 4C-3 / 4C-4 curve points
WARRANT3_CURVES = {
    '100': {
        (1, 1): [(400, 150), (500, 135), (600, 120), (700, 105), (800, 100), (900, 100), (1000, 100)],
        (2, 1): [(500, 150), (600, 135), (700, 120), (800, 105), (900, 100), (1000, 100), (1100, 100)],
        (2, 2): [(500, 200), (600, 180), (700, 160), (800, 150), (900, 150), (1000, 150), (1100, 150)],
        (1, 2): [(400, 200), (500, 180), (600, 160), (700, 150), (800, 150), (900, 150), (1000, 150)],
    },
    '70': {
        (1, 1): [(280, 105), (350, 95), (420, 84), (490, 74), (560, 70), (630, 70), (700, 70)],
        (2, 1): [(350, 105), (420, 95), (490, 84), (560, 74), (630, 70), (700, 70), (770, 70)],
        (2, 2): [(350, 140), (420, 126), (490, 112), (560, 105), (630, 105), (700, 105), (770, 105)],
        (1, 2): [(280, 140), (350, 126), (420, 112), (490, 105), (560, 105), (630, 105), (700, 105)],
    }
}

# Warrant 4: Pedestrian Volume - Figure 4C-5 through 4C-8
WARRANT4_CURVES = {
    'four_hour_100': [(300, 190), (400, 150), (500, 130), (600, 115), (700, 107), (800, 100), (900, 100), (1000, 100)],
    'four_hour_70': [(210, 133), (280, 105), (350, 91), (420, 81), (490, 75), (560, 70), (630, 70), (700, 70)],
    'peak_hour_100': [(300, 380), (400, 300), (500, 260), (600, 230), (700, 214), (800, 200), (900, 200), (1000, 200)],
    'peak_hour_70': [(210, 266), (280, 210), (350, 182), (420, 161), (490, 150), (560, 140), (630, 140), (700, 140)],
}


def get_lane_key(major_lanes, minor_lanes):
    """Convert actual lane counts to threshold table keys (1 or 2+)"""
    major = 1 if major_lanes == 1 else 2
    minor = 1 if minor_lanes == 1 else 2
    return (major, minor)


def get_threshold_percentage(speed, population, is_combination=False):
    """Determine which percentage column to use based on site conditions."""
    has_reduction = speed > 40 or population < 10000
    if is_combination:
        return '56' if has_reduction else '80'
    else:
        return '70' if has_reduction else '100'


def interpolate_threshold(curve_points, major_vol):
    """Given curve points and major volume, interpolate minor street threshold."""
    points = sorted(curve_points, key=lambda x: x[0])

    if major_vol < points[0][0]:
        return None
    if major_vol >= points[-1][0]:
        return points[-1][1]

    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        if x1 <= major_vol < x2:
            slope = (y2 - y1) / (x2 - x1)
            return y1 + slope * (major_vol - x1)

    return points[-1][1]


def evaluate_warrant1(traffic_df, major_lanes, minor_lanes, speed, population):
    """Evaluate Warrant 1: Eight-Hour Vehicular Volume"""
    if traffic_df is None or len(traffic_df) < 8:
        return {
            'met': None, 'condition': None, 'hours_met': 0,
            'details': 'Insufficient data (need at least 8 hours)',
            'threshold_used': None, 'hourly_results': None
        }

    lane_key = get_lane_key(major_lanes, minor_lanes)
    pct = get_threshold_percentage(speed, population, is_combination=False)
    pct_combo = get_threshold_percentage(speed, population, is_combination=True)

    thresh_a = WARRANT1_THRESHOLDS['condition_a'][lane_key][pct]
    thresh_b = WARRANT1_THRESHOLDS['condition_b'][lane_key][pct]
    thresh_a_combo = WARRANT1_THRESHOLDS['condition_a'][lane_key][pct_combo]
    thresh_b_combo = WARRANT1_THRESHOLDS['condition_b'][lane_key][pct_combo]

    street1_total = traffic_df['Street 1 (vph)'].sum()
    street2_total = traffic_df['Street 2 (vph)'].sum()

    if street1_total >= street2_total:
        major_col, minor_col = 'Street 1 (vph)', 'Street 2 (vph)'
    else:
        major_col, minor_col = 'Street 2 (vph)', 'Street 1 (vph)'

    hours_a = hours_b = hours_a_combo = hours_b_combo = 0
    hourly_results = []

    for idx, row in traffic_df.iterrows():
        major_vol = row[major_col]
        minor_vol = row[minor_col]

        meets_a = major_vol >= thresh_a[0] and minor_vol >= thresh_a[1]
        meets_b = major_vol >= thresh_b[0] and minor_vol >= thresh_b[1]
        meets_a_combo = major_vol >= thresh_a_combo[0] and minor_vol >= thresh_a_combo[1]
        meets_b_combo = major_vol >= thresh_b_combo[0] and minor_vol >= thresh_b_combo[1]

        if meets_a: hours_a += 1
        if meets_b: hours_b += 1
        if meets_a_combo: hours_a_combo += 1
        if meets_b_combo: hours_b_combo += 1

        hourly_results.append({
            'hour': row['Hour'], 'major_vol': major_vol, 'minor_vol': minor_vol,
            'meets_a': meets_a, 'meets_b': meets_b,
            'thresh_a_major': thresh_a[0], 'thresh_a_minor': thresh_a[1],
            'thresh_b_major': thresh_b[0], 'thresh_b_minor': thresh_b[1]
        })

    result = {
        'met': False, 'condition': None, 'hours_met': 0, 'details': '',
        'threshold_used': {'pct': pct, 'condition_a': thresh_a, 'condition_b': thresh_b},
        'hourly_results': hourly_results,
        'major_street': major_col.replace(' (vph)', ''),
        'minor_street': minor_col.replace(' (vph)', '')
    }

    if hours_a >= 8:
        result.update({'met': True, 'condition': 'A', 'hours_met': hours_a,
                       'details': f"Condition A MET: {hours_a} hours meet threshold ({pct}%)"})
    elif hours_b >= 8:
        result.update({'met': True, 'condition': 'B', 'hours_met': hours_b,
                       'details': f"Condition B MET: {hours_b} hours meet threshold ({pct}%)"})
    elif hours_a_combo >= 8 and hours_b_combo >= 8:
        result.update({'met': True, 'condition': 'A+B', 'hours_met': min(hours_a_combo, hours_b_combo),
                       'details': f"Combination A+B MET: Both conditions meet {pct_combo}% threshold for 8+ hours"})
    else:
        result.update({'met': False, 'hours_met': max(hours_a, hours_b),
                       'details': f"NOT MET: Condition A ({hours_a}/8 hrs), Condition B ({hours_b}/8 hrs)"})

    return result


def evaluate_warrant2(traffic_df, major_lanes, minor_lanes, speed, population):
    """Evaluate Warrant 2: Four-Hour Vehicular Volume"""
    if traffic_df is None or len(traffic_df) < 4:
        return {
            'met': None, 'hours_met': 0,
            'details': 'Insufficient data (need at least 4 hours)',
            'hourly_results': None, 'curve_points': None
        }

    lane_key = get_lane_key(major_lanes, minor_lanes)
    pct = '70' if (speed > 40 or population < 10000) else '100'
    curve_points = WARRANT2_CURVES[pct][lane_key]

    street1_total = traffic_df['Street 1 (vph)'].sum()
    street2_total = traffic_df['Street 2 (vph)'].sum()

    if street1_total >= street2_total:
        major_col, minor_col = 'Street 1 (vph)', 'Street 2 (vph)'
    else:
        major_col, minor_col = 'Street 2 (vph)', 'Street 1 (vph)'

    hours_above = 0
    hourly_results = []

    for idx, row in traffic_df.iterrows():
        major_vol = row[major_col]
        minor_vol = row[minor_col]

        threshold = interpolate_threshold(curve_points, major_vol)
        above_curve = threshold is not None and minor_vol >= threshold

        if above_curve:
            hours_above += 1

        hourly_results.append({
            'hour': row['Hour'], 'major_vol': major_vol, 'minor_vol': minor_vol,
            'threshold': threshold, 'above_curve': above_curve
        })

    return {
        'met': hours_above >= 4,
        'hours_met': hours_above,
        'details': f"{'MET' if hours_above >= 4 else 'NOT MET'}: {hours_above}/4 hours above curve ({pct}%)",
        'hourly_results': hourly_results,
        'curve_points': curve_points,
        'pct': pct,
        'major_street': major_col.replace(' (vph)', ''),
        'minor_street': minor_col.replace(' (vph)', '')
    }


def evaluate_warrant3(traffic_df, major_lanes, minor_lanes, speed, population):
    """Evaluate Warrant 3: Peak Hour"""
    if traffic_df is None or len(traffic_df) < 1:
        return {
            'met': None, 'details': 'Insufficient data',
            'peak_hour': None, 'curve_points': None
        }

    lane_key = get_lane_key(major_lanes, minor_lanes)
    pct = '70' if (speed > 40 or population < 10000) else '100'
    curve_points = WARRANT3_CURVES[pct][lane_key]

    street1_total = traffic_df['Street 1 (vph)'].sum()
    street2_total = traffic_df['Street 2 (vph)'].sum()

    if street1_total >= street2_total:
        major_col, minor_col = 'Street 1 (vph)', 'Street 2 (vph)'
    else:
        major_col, minor_col = 'Street 2 (vph)', 'Street 1 (vph)'

    traffic_df = traffic_df.copy()
    traffic_df['total'] = traffic_df[major_col] + traffic_df[minor_col]
    peak_idx = traffic_df['total'].idxmax()
    peak_row = traffic_df.loc[peak_idx]

    peak_major = peak_row[major_col]
    peak_minor = peak_row[minor_col]
    peak_hour = peak_row['Hour']

    threshold = interpolate_threshold(curve_points, peak_major)
    above_curve = threshold is not None and peak_minor >= threshold

    detail_str = f"{'MET' if above_curve else 'NOT MET'}: Peak hour ({peak_hour}) - {peak_minor:.0f} vph vs {threshold:.0f} vph threshold ({pct}%)" if threshold else "NOT MET: Major volume below curve range"

    return {
        'met': above_curve,
        'peak_hour': peak_hour,
        'peak_major': peak_major,
        'peak_minor': peak_minor,
        'threshold': threshold,
        'details': detail_str,
        'curve_points': curve_points,
        'pct': pct,
        'major_street': major_col.replace(' (vph)', ''),
        'minor_street': minor_col.replace(' (vph)', '')
    }


def evaluate_warrant4(traffic_df, speed, population, ped_peak, ped_4hr, gaps_per_hour, dist_to_signal):
    """Evaluate Warrant 4: Pedestrian Volume"""
    if dist_to_signal < 300:
        return {
            'met': False,
            'details': 'NOT MET: Distance to nearest signal < 300 ft',
            'criterion': None,
            'four_hour_met': False,
            'peak_hour_met': False
        }

    gaps_ok = gaps_per_hour < 60

    if not gaps_ok:
        return {
            'met': False,
            'details': f'NOT MET: Adequate gaps ({gaps_per_hour}/hr) >= 60 required maximum',
            'criterion': None,
            'four_hour_met': False,
            'peak_hour_met': False
        }

    use_70 = speed > 35 or population < 10000
    pct = '70' if use_70 else '100'

    four_hour_curve = WARRANT4_CURVES[f'four_hour_{pct}']
    peak_hour_curve = WARRANT4_CURVES[f'peak_hour_{pct}']

    if traffic_df is None or len(traffic_df) < 1:
        return {
            'met': None,
            'details': 'Insufficient traffic data',
            'criterion': None,
            'four_hour_met': False,
            'peak_hour_met': False
        }

    street1_total = traffic_df['Street 1 (vph)'].sum()
    street2_total = traffic_df['Street 2 (vph)'].sum()
    major_col = 'Street 1 (vph)' if street1_total >= street2_total else 'Street 2 (vph)'

    top_4_major = traffic_df.nlargest(4, major_col)[major_col].mean()
    four_hr_threshold = interpolate_threshold(four_hour_curve, top_4_major)
    four_hour_met = four_hr_threshold is not None and ped_4hr >= four_hr_threshold

    peak_major = traffic_df[major_col].max()
    peak_hr_threshold = interpolate_threshold(peak_hour_curve, peak_major)
    peak_hour_met = peak_hr_threshold is not None and ped_peak >= peak_hr_threshold

    met = four_hour_met or peak_hour_met

    if met:
        criterion = 'Four-Hour' if four_hour_met else 'Peak Hour'
        if four_hour_met:
            details = f"MET ({criterion}): {ped_4hr} peds/hr vs {four_hr_threshold:.0f} threshold ({pct}%)"
        else:
            details = f"MET ({criterion}): {ped_peak} peds/hr vs {peak_hr_threshold:.0f} threshold ({pct}%)"
    else:
        four_hr_str = f"{four_hr_threshold:.0f}" if four_hr_threshold else "N/A"
        peak_hr_str = f"{peak_hr_threshold:.0f}" if peak_hr_threshold else "N/A"
        details = f"NOT MET: 4-hr ({ped_4hr} vs {four_hr_str}), Peak ({ped_peak} vs {peak_hr_str}) ({pct}%)"
        criterion = None

    return {
        'met': met,
        'details': details,
        'criterion': criterion,
        'four_hour_met': four_hour_met,
        'peak_hour_met': peak_hour_met,
        'four_hour_threshold': four_hr_threshold,
        'peak_hour_threshold': peak_hr_threshold,
        'pct': pct,
        'gaps_per_hour': gaps_per_hour,
        'four_hour_curve': four_hour_curve,
        'peak_hour_curve': peak_hour_curve
    }


def evaluate_warrant5(school_crossing, school_children, school_gaps, crossing_period_minutes=30):
    """Evaluate Warrant 5: School Crossing"""
    if not school_crossing:
        return {
            'met': None,
            'details': 'No school crossing designated',
            'children': school_children,
            'gaps': school_gaps
        }

    if school_children < 20:
        return {
            'met': False,
            'details': f'NOT MET: {school_children} schoolchildren < 20 minimum',
            'children': school_children,
            'gaps': school_gaps
        }

    gaps_ok = school_gaps < crossing_period_minutes

    if gaps_ok:
        return {
            'met': True,
            'details': f'MET: {school_children} children, {school_gaps} gaps < {crossing_period_minutes} min period',
            'children': school_children,
            'gaps': school_gaps
        }
    else:
        return {
            'met': False,
            'details': f'NOT MET: {school_gaps} adequate gaps >= {crossing_period_minutes} min crossing period',
            'children': school_children,
            'gaps': school_gaps
        }


def evaluate_warrant6(coordinated_system, signal_spacing, progression_speed):
    """
    Evaluate Warrant 6: Coordinated Signal System

    This warrant is met when:
    - Intersection is part of a coordinated signal system
    - Signals are spaced appropriately for progression
    - Installation would improve coordination

    Note: This is primarily an engineering judgment warrant
    """
    if not coordinated_system:
        return {
            'met': None,
            'details': 'Not part of coordinated system',
            'signal_spacing': signal_spacing,
            'progression_speed': progression_speed
        }

    # MUTCD guidance: signals should be spaced for good progression
    # Typical guidance: 1000-2640 ft spacing depending on progression speed
    min_spacing = 1000  # feet
    max_spacing = 2640  # feet (half mile)

    spacing_ok = min_spacing <= signal_spacing <= max_spacing

    if spacing_ok:
        return {
            'met': True,
            'details': f'MET: {signal_spacing} ft spacing within {min_spacing}-{max_spacing} ft range',
            'signal_spacing': signal_spacing,
            'progression_speed': progression_speed,
            'engineering_judgment': True
        }
    else:
        return {
            'met': False,
            'details': f'NOT MET: {signal_spacing} ft spacing outside {min_spacing}-{max_spacing} ft range',
            'signal_spacing': signal_spacing,
            'progression_speed': progression_speed,
            'engineering_judgment': True
        }


def evaluate_warrant7(traffic_df, major_lanes, minor_lanes, speed, population,
                      correctable_crashes, alternatives_tried):
    """
    Evaluate Warrant 7: Crash Experience

    MUTCD 2009 Section 4C.08 requires ALL of the following:

    A. Adequate trial of alternatives with satisfactory observance and enforcement
       has failed to reduce the crash frequency

    B. Five or more reported crashes of types susceptible to correction by a
       traffic control signal have occurred within a 12-month period

    C. For each of any 8 hours of an average day, the traffic volumes meet EITHER:
       - 80% of Warrant 1 (Table 4C-1) Condition A OR Condition B thresholds, OR
       - The volumes fall above the applicable curve in Figure 4C-3 or 4C-4 (Warrant 3)

    Crash types correctable by signal: right-angle, left-turn, pedestrian
    """
    # Check alternatives requirement (Condition A)
    if not alternatives_tried:
        return {
            'met': False,
            'details': 'NOT MET: Adequate trial of alternatives not documented',
            'condition_a': False,
            'condition_b': False,
            'condition_c': False,
            'correctable_crashes': correctable_crashes,
            'hours_meeting_volume': 0
        }

    # Check crash requirement (Condition B) - 5+ in 12 months
    if correctable_crashes < 5:
        return {
            'met': False,
            'details': f'NOT MET: {correctable_crashes} correctable crashes < 5 required (12-month period)',
            'condition_a': True,
            'condition_b': False,
            'condition_c': False,
            'correctable_crashes': correctable_crashes,
            'hours_meeting_volume': 0
        }

    # Check volume requirement (Condition C)
    if traffic_df is None or len(traffic_df) < 8:
        return {
            'met': False,
            'details': 'NOT MET: Insufficient traffic data for volume analysis',
            'condition_a': True,
            'condition_b': True,
            'condition_c': False,
            'correctable_crashes': correctable_crashes,
            'hours_meeting_volume': 0
        }

    lane_key = get_lane_key(major_lanes, minor_lanes)

    # Get 80% thresholds from Warrant 1
    thresh_a_80 = WARRANT1_THRESHOLDS['condition_a'][lane_key]['80']
    thresh_b_80 = WARRANT1_THRESHOLDS['condition_b'][lane_key]['80']

    # Get Warrant 3 curve (use 100% for Warrant 7 per MUTCD)
    pct = '70' if (speed > 40 or population < 10000) else '100'
    curve_points = WARRANT3_CURVES[pct][lane_key]

    # Determine major/minor streets
    street1_total = traffic_df['Street 1 (vph)'].sum()
    street2_total = traffic_df['Street 2 (vph)'].sum()

    if street1_total >= street2_total:
        major_col, minor_col = 'Street 1 (vph)', 'Street 2 (vph)'
    else:
        major_col, minor_col = 'Street 2 (vph)', 'Street 1 (vph)'

    hours_meeting_volume = 0
    hourly_results = []

    for idx, row in traffic_df.iterrows():
        major_vol = row[major_col]
        minor_vol = row[minor_col]

        # Check 80% of Warrant 1 Condition A
        meets_w1_a = major_vol >= thresh_a_80[0] and minor_vol >= thresh_a_80[1]

        # Check 80% of Warrant 1 Condition B
        meets_w1_b = major_vol >= thresh_b_80[0] and minor_vol >= thresh_b_80[1]

        # Check Warrant 3 curve
        w3_threshold = interpolate_threshold(curve_points, major_vol)
        meets_w3 = w3_threshold is not None and minor_vol >= w3_threshold

        meets_volume = meets_w1_a or meets_w1_b or meets_w3

        if meets_volume:
            hours_meeting_volume += 1

        hourly_results.append({
            'hour': row['Hour'],
            'major_vol': major_vol,
            'minor_vol': minor_vol,
            'meets_w1_a': meets_w1_a,
            'meets_w1_b': meets_w1_b,
            'meets_w3': meets_w3,
            'meets_volume': meets_volume,
            'thresh_a': thresh_a_80,
            'thresh_b': thresh_b_80,
            'w3_threshold': w3_threshold
        })

    condition_c_met = hours_meeting_volume >= 8

    if condition_c_met:
        return {
            'met': True,
            'details': f'MET: {correctable_crashes} crashes, alternatives tried, {hours_meeting_volume}/8 hrs volume',
            'condition_a': True,
            'condition_b': True,
            'condition_c': True,
            'correctable_crashes': correctable_crashes,
            'hours_meeting_volume': hours_meeting_volume,
            'hourly_results': hourly_results,
            'thresh_a_80': thresh_a_80,
            'thresh_b_80': thresh_b_80,
            'curve_points': curve_points,
            'pct': pct,
            'major_street': major_col.replace(' (vph)', ''),
            'minor_street': minor_col.replace(' (vph)', '')
        }
    else:
        return {
            'met': False,
            'details': f'NOT MET: Volume requirement - only {hours_meeting_volume}/8 hours meet threshold',
            'condition_a': True,
            'condition_b': True,
            'condition_c': False,
            'correctable_crashes': correctable_crashes,
            'hours_meeting_volume': hours_meeting_volume,
            'hourly_results': hourly_results,
            'thresh_a_80': thresh_a_80,
            'thresh_b_80': thresh_b_80,
            'curve_points': curve_points,
            'pct': pct,
            'major_street': major_col.replace(' (vph)', ''),
            'minor_street': minor_col.replace(' (vph)', '')
        }


def evaluate_warrant8(network_continuity, route_designation, future_volumes):
    """
    Evaluate Warrant 8: Roadway Network

    This warrant is satisfied when:
    - Installation would encourage concentration of traffic on a roadway network
    - Projected volumes would meet Warrant 1 or 2 within 5 years
    - Intersection is on designated routes (arterials)

    Note: This is primarily an engineering judgment warrant
    """
    if not network_continuity:
        return {
            'met': None,
            'details': 'Network continuity not applicable',
            'route_designation': route_designation,
            'future_volumes': future_volumes,
            'engineering_judgment': True
        }

    if route_designation and future_volumes:
        return {
            'met': True,
            'details': f'MET: Route designation confirmed, projected volumes support installation',
            'route_designation': route_designation,
            'future_volumes': future_volumes,
            'engineering_judgment': True
        }
    elif route_designation:
        return {
            'met': False,
            'details': 'NOT MET: Route designated but projected volumes insufficient',
            'route_designation': route_designation,
            'future_volumes': future_volumes,
            'engineering_judgment': True
        }
    else:
        return {
            'met': False,
            'details': 'NOT MET: Not on designated route network',
            'route_designation': route_designation,
            'future_volumes': future_volumes,
            'engineering_judgment': True
        }


def evaluate_warrant9(railroad_crossing, train_frequency, queuing_distance, preemption_needed):
    """
    Evaluate Warrant 9: Intersection Near a Grade Crossing

    This warrant applies when:
    - Intersection is within 140 ft of a railroad grade crossing
    - Traffic control signal would prevent queuing across tracks
    - Preemption of the signal by approaching trains is needed

    Note: This warrant has specific geometric and operational requirements
    """
    if not railroad_crossing:
        return {
            'met': None,
            'details': 'No railroad grade crossing nearby',
            'train_frequency': train_frequency,
            'queuing_distance': queuing_distance,
            'preemption_needed': preemption_needed
        }

    # Check distance requirement (within 140 ft per MUTCD)
    if queuing_distance > 140:
        return {
            'met': False,
            'details': f'NOT MET: Distance ({queuing_distance} ft) exceeds 140 ft maximum',
            'train_frequency': train_frequency,
            'queuing_distance': queuing_distance,
            'preemption_needed': preemption_needed
        }

    if train_frequency > 0 and preemption_needed:
        return {
            'met': True,
            'details': f'MET: {train_frequency} trains/day, {queuing_distance} ft from crossing, preemption required',
            'train_frequency': train_frequency,
            'queuing_distance': queuing_distance,
            'preemption_needed': preemption_needed
        }
    else:
        return {
            'met': False,
            'details': 'NOT MET: Insufficient train activity or preemption not needed',
            'train_frequency': train_frequency,
            'queuing_distance': queuing_distance,
            'preemption_needed': preemption_needed
        }


# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================

def generate_excel_report(results_df, traffic_df, project_info):
    """Generate Excel workbook with warrant analysis results"""
    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Summary sheet
        results_df.to_excel(writer, sheet_name='Warrant Summary', index=False)

        # Traffic data sheet
        if traffic_df is not None:
            traffic_df.to_excel(writer, sheet_name='Traffic Counts', index=False)

        # Project info sheet
        info_df = pd.DataFrame([
            ['Project Name', project_info.get('project_name', '')],
            ['Location', project_info.get('location', '')],
            ['Street 1', project_info.get('street_1', '')],
            ['Street 2', project_info.get('street_2', '')],
            ['Approach Speed (mph)', project_info.get('approach_speed', '')],
            ['Population', project_info.get('population', '')],
            ['Lanes - Street 1', project_info.get('lanes_1', '')],
            ['Lanes - Street 2', project_info.get('lanes_2', '')],
            ['Distance to Signal (ft)', project_info.get('dist_signal', '')],
            ['Report Generated', datetime.now().strftime('%Y-%m-%d %H:%M')]
        ], columns=['Parameter', 'Value'])
        info_df.to_excel(writer, sheet_name='Project Info', index=False)

    output.seek(0)
    return output


def generate_csv_report(results_df):
    """Generate CSV of warrant summary"""
    output = BytesIO()
    results_df.to_csv(output, index=False)
    output.seek(0)
    return output


def generate_pdf_report(results_df, traffic_df, project_info, warrant_results):
    """Generate professional PDF report of warrant analysis"""
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch)

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=20,
        textColor=colors.HexColor('#1e2a3a')
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=15,
        spaceAfter=10,
        textColor=colors.HexColor('#1e2a3a')
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
    )

    story = []

    # Title
    story.append(Paragraph("MUTCD Signal Warrant Analysis Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}", normal_style))
    story.append(Spacer(1, 20))

    # Project Information
    story.append(Paragraph("Project Information", heading_style))

    project_data = [
        ['Project Name:', project_info.get('project_name', 'N/A')],
        ['Location:', project_info.get('location', 'N/A')],
        ['Street 1:', project_info.get('street_1', 'N/A')],
        ['Street 2:', project_info.get('street_2', 'N/A')],
        ['Approach Speed:', f"{project_info.get('approach_speed', 'N/A')} mph"],
        ['Population:', f"{project_info.get('population', 'N/A'):,}" if project_info.get('population') else 'N/A'],
        ['Lane Configuration:', f"{project_info.get('lanes_1', 'N/A')} x {project_info.get('lanes_2', 'N/A')}"],
        ['Distance to Nearest Signal:', f"{project_info.get('dist_signal', 'N/A')} ft"],
    ]

    project_table = Table(project_data, colWidths=[2 * inch, 4 * inch])
    project_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(project_table)
    story.append(Spacer(1, 20))

    # Warrant Analysis Summary
    story.append(Paragraph("Warrant Analysis Summary", heading_style))

    # Count met warrants
    met_count = sum(1 for _, row in results_df.iterrows() if '✓' in str(row['Status']))
    if met_count > 0:
        story.append(
            Paragraph(f"<b>{met_count} warrant(s) satisfied</b> — Signal installation may be justified", normal_style))
    else:
        story.append(Paragraph("<b>No warrants currently satisfied</b> — Additional data or conditions may be needed",
                               normal_style))
    story.append(Spacer(1, 10))

    # Results table
    table_data = [['Warrant', 'Status', 'Data', 'Threshold']]
    for _, row in results_df.iterrows():
        table_data.append([
            row['Warrant'],
            row['Status'],
            row['Data'],
            row['Threshold']
        ])

    results_table = Table(table_data, colWidths=[1.8 * inch, 1 * inch, 1.5 * inch, 1.5 * inch])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e2a3a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(results_table)
    story.append(Spacer(1, 20))

    # Detailed Notes
    story.append(Paragraph("Detailed Analysis Notes", heading_style))
    for _, row in results_df.iterrows():
        if row['Notes'] and row['Notes'] != '—':
            story.append(Paragraph(f"<b>{row['Warrant']}:</b> {row['Notes']}", normal_style))

    story.append(PageBreak())

    # Traffic Data (if available)
    if traffic_df is not None and len(traffic_df) > 0:
        story.append(Paragraph("Traffic Count Data", heading_style))

        traffic_table_data = [['Hour', 'Street 1 (vph)', 'Street 2 (vph)']]
        for _, row in traffic_df.iterrows():
            traffic_table_data.append([
                str(row['Hour']),
                str(int(row['Street 1 (vph)'])),
                str(int(row['Street 2 (vph)']))
            ])

        traffic_table = Table(traffic_table_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch])
        traffic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e2a3a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ]))
        story.append(traffic_table)
        story.append(Spacer(1, 20))

    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph("—" * 60, normal_style))
    story.append(Paragraph("Report generated by MUTCD Warrant Pro | MUTCD 2009 Edition",
                           ParagraphStyle('Footer', parent=normal_style, fontSize=8, textColor=colors.grey)))
    story.append(Paragraph(
        "This analysis is for planning purposes only. Final signal installation decisions should be made by a licensed Professional Engineer.",
        ParagraphStyle('Disclaimer', parent=normal_style, fontSize=8, textColor=colors.grey)))

    doc.build(story)
    output.seek(0)
    return output


# =============================================================================
# STREAMLIT UI
# =============================================================================

st.set_page_config(
    page_title="MUTCD Warrant Pro",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background-color: #1e2a3a;
        padding-top: 0;
    }
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        color: #b0bec5 !important;
        padding: 8px 0;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        color: #ffffff !important;
    }
    .main .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }
    h1 {
        color: #1e2a3a;
        font-weight: 600;
        margin-bottom: 1.5rem;
    }
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
        padding: 0.5rem 1.5rem;
    }
 /* Secondary buttons only */
    button[data-testid="baseButton-secondary"] {
        font-size: 0.85rem;
    }
    .version-indicator {
        background-color: #2d3e50;
        border-radius: 4px;
        padding: 8px 12px;
        margin: 10px 0;
        font-size: 0.8rem;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'Project Details'

if 'project_data' not in st.session_state:
    st.session_state.project_data = {
        'project_name': '', 'location': '', 'street_1': '', 'street_2': '',
        'approach_speed': 35, 'area_type': 'Urban', 'population': 10000,
        'lanes_street_1': 2, 'lanes_street_2': 1, 'distance_to_signal': 1000,
    }

if 'traffic_data' not in st.session_state:
    st.session_state.traffic_data = None

if 'analysis_run' not in st.session_state:
    st.session_state.analysis_run = False

# Sidebar
with st.sidebar:
    st.markdown("### 🚦 MUTCD Warrant Pro")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        ["Project Details", "Traffic Counts", "Pedestrian/Bike", "Crash Data",
         "Network/Coordination", "About"],
        label_visibility="collapsed"
    )
    st.session_state.current_page = page

    st.markdown("---")

    st.markdown("""
    <div class="version-indicator">
        <strong>MUTCD Version</strong><br>
        2009 Edition
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    if st.button("📊 Run Analysis", use_container_width=True, type="primary"):
        st.session_state.analysis_run = True
        st.rerun()

    st.markdown("---")
    st.caption("📥 Export options available after running analysis on the Traffic Counts page")


def render_project_details():
    st.markdown("## Project Details")

    col1, col2 = st.columns(2)

    with col1:
        st.text_input("Project Name", key="project_name",
                      value=st.session_state.project_data['project_name'],
                      placeholder="Enter project name")
        st.text_input("Location/Description", key="location",
                      placeholder="e.g., Main St & Oak Ave")

        st.subheader("Street Information")
        st.text_input("Street 1 Name", key="street_1", placeholder="e.g., Main Street")
        st.text_input("Street 2 Name", key="street_2", placeholder="e.g., Oak Avenue")
        st.caption("System will auto-assign major/minor based on volumes")

    with col2:
        st.subheader("Site Characteristics")
        st.number_input("Approach Speed (mph)", min_value=15, max_value=70, value=35, key="approach_speed",
                        help="Posted speed limit or 85th percentile speed on major street")
        st.selectbox("Area Type", ["Urban", "Rural"], key="area_type")
        st.number_input("Community Population", min_value=100, max_value=10000000,
                        value=10000, key="population",
                        help="Used for 70% threshold reduction if < 10,000")

        st.subheader("Lane Configuration")
        st.number_input("Lanes - Street 1", min_value=1, max_value=6, value=2, key="lanes_1")
        st.number_input("Lanes - Street 2", min_value=1, max_value=6, value=1, key="lanes_2")
        st.number_input("Distance to Nearest Signal (ft)", min_value=0, max_value=10000,
                        value=1000, key="dist_signal")


def render_traffic_counts():
    st.markdown("## Traffic Counts (Hourly)")

    st.info(
        "Enter 12-16 hours of turning movement counts. Street 1 = total of both approaches. Street 2 = higher-volume approach (one direction).")

    col1, col2 = st.columns([2, 1])

    with col1:

        if 'traffic_df' not in st.session_state:
            hours = [f"{h}:00" for h in range(6, 22)]
            st.session_state.traffic_df = pd.DataFrame({
                'Hour': hours,
                'Street 1 (vph)': [0] * 16,
                'Street 2 (vph)': [0] * 16
            })

        street1_name = st.session_state.get('street_1', 'Street 1') or 'Street 1'
        street2_name = st.session_state.get('street_2', 'Street 2') or 'Street 2'

        st.caption(
            f"**{street1_name}**: Total both approaches  |  **{street2_name}**: Higher-volume approach (one direction)")

        edited_df = st.data_editor(
            st.session_state.traffic_df,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Hour": st.column_config.TextColumn("Hour", disabled=True, width="small"),
                "Street 1 (vph)": st.column_config.NumberColumn(f"{street1_name} (vph)", min_value=0, max_value=9999,
                                                                step=1, format="%d"),
                "Street 2 (vph)": st.column_config.NumberColumn(f"{street2_name} (vph)", min_value=0, max_value=9999,
                                                                step=1, format="%d"),
            }
        )
        st.session_state.traffic_df = edited_df

    with col2:

        st.subheader("CSV Upload")
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'], label_visibility="collapsed")
        if uploaded_file:
            try:
                csv_df = pd.read_csv(uploaded_file)
                if 'Hour' in csv_df.columns and len(csv_df.columns) >= 3:
                    csv_df.columns = ['Hour', 'Street 1 (vph)', 'Street 2 (vph)'][:len(csv_df.columns)]
                    st.session_state.traffic_df = csv_df
                    st.success("CSV loaded")
                    st.rerun()
                else:
                    st.error("CSV must have Hour, Street 1, Street 2 columns")
            except Exception as e:
                st.error(f"Error reading CSV: {e}")

        st.markdown("---")
        st.subheader("Data Summary")
        df = st.session_state.traffic_df
        total_s1 = df['Street 1 (vph)'].sum()
        total_s2 = df['Street 2 (vph)'].sum()
        hours_with_data = len(df[(df['Street 1 (vph)'] > 0) | (df['Street 2 (vph)'] > 0)])

        st.metric("Hours with data", hours_with_data)
        st.metric("Street 1 Total", f"{total_s1:,} vph")
        st.metric("Street 2 Total", f"{total_s2:,} vph")

        if total_s1 >= total_s2:
            st.caption("→ Street 1 = Major")
        else:
            st.caption("→ Street 2 = Major")


def render_pedestrian_bike():
    st.markdown("## Pedestrian & Bicycle Data")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Pedestrian Counts")
        st.number_input("Peak Hour Pedestrians (crossing major street)",
                        min_value=0, max_value=5000, value=0, key="ped_peak")
        st.number_input("4-Hour Average Pedestrians/Hour",
                        min_value=0, max_value=2000, value=0, key="ped_4hr")

        st.subheader("Gap Study")
        st.number_input("Adequate Gaps per Hour", min_value=0, max_value=200, value=60, key="gaps",
                        help="Number of gaps adequate for pedestrian crossing")

    with col2:
        st.subheader("School Crossing (Warrant 5)")
        st.checkbox("School crossing present", key="school_crossing")
        st.number_input("Schoolchildren at Peak Crossing Hour",
                        min_value=0, max_value=500, value=0, key="school_children")
        st.number_input("Adequate Gaps During School Crossing",
                        min_value=0, max_value=200, value=0, key="school_gaps")


def render_crash_data():
    st.markdown("## Crash Data (Warrant 7)")

    st.info(
        "📋 **MUTCD Requirement:** 5+ crashes correctable by signal within a **12-month period**, plus volume thresholds and documented trial of alternatives.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("12-Month Crash History")
        st.number_input("Total Reportable Crashes (12 months)", min_value=0, max_value=100, value=0,
                        key="total_crashes",
                        help="All crashes meeting state reporting threshold in the past 12 months")
        st.number_input("Crashes Correctable by Signal", min_value=0, max_value=100, value=0,
                        key="correctable_crashes",
                        help="Right-angle, left-turn, and pedestrian crashes typically correctable by signal")

    with col2:
        st.subheader("Crash Types (12 months)")
        st.number_input("Right-Angle Crashes", min_value=0, max_value=50, value=0, key="right_angle",
                        help="T-bone type crashes - correctable by signal")
        st.number_input("Left-Turn Crashes", min_value=0, max_value=50, value=0, key="left_turn",
                        help="Opposing left-turn crashes - correctable by signal")
        st.number_input("Pedestrian Crashes", min_value=0, max_value=50, value=0, key="ped_crashes",
                        help="Crashes involving pedestrians - correctable by signal")

    st.subheader("Other Measures Attempted")
    st.checkbox("Adequate trial of alternatives completed", key="alternatives_tried",
                help="**Required for Warrant 7** - other remedial measures must have been attempted and failed")
    st.text_area("Describe alternatives attempted", key="alternatives_desc",
                 placeholder="e.g., Enhanced signing, improved sight distance, increased enforcement, geometric improvements...")

    if st.session_state.get('alternatives_tried', False):
        st.success("✓ Alternatives requirement documented")
    else:
        st.warning("⚠ Document alternatives tried before Warrant 7 can be satisfied")


def render_network_coordination():
    """Render inputs for Warrants 6, 8, and 9"""
    st.markdown("## Network, Coordination & Grade Crossing")

    st.info(
        "ℹ️ These warrants involve significant engineering judgment. Check applicable boxes and provide supporting data.")

    col1, col2 = st.columns(2)

    with col1:
        # Warrant 6: Coordinated Signal System

        st.subheader("Warrant 6: Coordinated Signal System")
        st.checkbox("Part of coordinated signal system", key="coordinated_system",
                    help="Intersection is or will be part of a coordinated arterial signal system")
        st.number_input("Distance to Adjacent Signals (ft)", min_value=0, max_value=10000,
                        value=2000, key="signal_spacing",
                        help="Typical good progression: 1000-2640 ft")
        st.number_input("Progression Speed (mph)", min_value=15, max_value=55,
                        value=35, key="progression_speed",
                        help="Design speed for signal coordination")

        # Warrant 8: Roadway Network

        st.subheader("Warrant 8: Roadway Network")
        st.checkbox("Network continuity consideration", key="network_continuity",
                    help="Installation would encourage traffic concentration on proper roadway network")
        st.checkbox("On designated arterial/collector route", key="route_designation",
                    help="Intersection is on a designated route in the transportation plan")
        st.checkbox("Projected volumes meet warrants within 5 years", key="future_volumes",
                    help="Traffic projections show warrant conditions will be met")

    with col2:
        # Warrant 9: Grade Crossing

        st.subheader("Warrant 9: Intersection Near Grade Crossing")
        st.checkbox("Railroad grade crossing nearby", key="railroad_crossing",
                    help="Intersection is near an at-grade railroad crossing")
        st.number_input("Distance to Railroad Crossing (ft)", min_value=0, max_value=500,
                        value=200, key="queuing_distance",
                        help="MUTCD requires within 140 ft for this warrant")
        st.number_input("Train Frequency (trains/day)", min_value=0, max_value=200,
                        value=0, key="train_frequency")
        st.checkbox("Signal preemption required", key="preemption_needed",
                    help="Preemption by approaching trains would improve safety")

        # Engineering Notes

        st.subheader("Engineering Judgment Notes")
        st.text_area("Additional considerations", key="eng_notes",
                     placeholder="Document any special circumstances, future development, or other factors supporting signal installation...",
                     height=150)


def render_settings():
    st.markdown("## About / Analysis Rules")

    st.info("ℹ️ This section shows the rules and thresholds used by this tool. All values are per MUTCD 2009 Edition.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📐 Thresholds Applied")
        st.markdown("""
        **MUTCD Edition:** 2009

        **70% Threshold Reduction** is automatically applied when:
        - Warrants 1, 2, 3: Speed > 40 mph OR Population < 10,000
        - Warrant 4 (Pedestrian): Speed > 35 mph OR Population < 10,000

        **Major/Minor Street Assignment:**  
        Automatically determined by total volume (higher = major)
        """)

        st.subheader("📊 Warrant Requirements")
        st.markdown("""
        | Warrant | Requirement |
        |---------|-------------|
        | 1 | 8 hours meet threshold |
        | 2 | 4 hours above curve |
        | 3 | Peak hour above curve |
        | 4 | Pedestrian volume + gaps < 60/hr |
        | 5 | ≥20 children + gaps < period |
        | 6 | Engineering judgment |
        | 7 | ≥5 crashes + 80% volume + alternatives |
        | 8 | Engineering judgment |
        | 9 | ≤140 ft to railroad |
        """)

    with col2:
        st.subheader("📋 Data Entry Guidelines")
        st.markdown("""
        **Traffic Counts:**
        - Street 1: Total of both approaches
        - Street 2: Higher-volume approach (one direction)
        - Enter 8-16 hours for full analysis

        **Crash Data (Warrant 7):**
        - Use 12-month crash history
        - Count only signal-correctable types (right-angle, left-turn, pedestrian)

        **Pedestrian Data:**
        - Peak hour = single highest hour
        - 4-hour average = mean of 4 highest hours
        """)

        st.subheader("📄 Export Formats")
        st.markdown("""
        - **PDF:** Full report with charts description
        - **Excel:** Multi-sheet workbook with all data
        - **CSV:** Summary table only
        """)


def render_results():
    """Render the warrant analysis results"""
    st.markdown("## Warrant Analysis Results")

    traffic_df = st.session_state.get('traffic_df', None)
    major_lanes = st.session_state.get('lanes_1', 2)
    minor_lanes = st.session_state.get('lanes_2', 1)
    speed = st.session_state.get('approach_speed', 35)
    population = st.session_state.get('population', 10000)

    # Pedestrian data
    ped_peak = st.session_state.get('ped_peak', 0)
    ped_4hr = st.session_state.get('ped_4hr', 0)
    gaps = st.session_state.get('gaps', 60)
    dist_signal = st.session_state.get('dist_signal', 1000)

    # School data
    school_crossing = st.session_state.get('school_crossing', False)
    school_children = st.session_state.get('school_children', 0)
    school_gaps = st.session_state.get('school_gaps', 0)

    # Crash data
    correctable_crashes = st.session_state.get('correctable_crashes', 0)
    alternatives_tried = st.session_state.get('alternatives_tried', False)

    # Warrant 6 data
    coordinated_system = st.session_state.get('coordinated_system', False)
    signal_spacing = st.session_state.get('signal_spacing', 2000)
    progression_speed = st.session_state.get('progression_speed', 35)

    # Warrant 8 data
    network_continuity = st.session_state.get('network_continuity', False)
    route_designation = st.session_state.get('route_designation', False)
    future_volumes = st.session_state.get('future_volumes', False)

    # Warrant 9 data
    railroad_crossing = st.session_state.get('railroad_crossing', False)
    queuing_distance = st.session_state.get('queuing_distance', 200)
    train_frequency = st.session_state.get('train_frequency', 0)
    preemption_needed = st.session_state.get('preemption_needed', False)

    # Evaluate all warrants
    w1_result = evaluate_warrant1(traffic_df, major_lanes, minor_lanes, speed, population)
    w2_result = evaluate_warrant2(traffic_df, major_lanes, minor_lanes, speed, population)
    w3_result = evaluate_warrant3(traffic_df, major_lanes, minor_lanes, speed, population)
    w4_result = evaluate_warrant4(traffic_df, speed, population, ped_peak, ped_4hr, gaps, dist_signal)
    w5_result = evaluate_warrant5(school_crossing, school_children, school_gaps)
    w6_result = evaluate_warrant6(coordinated_system, signal_spacing, progression_speed)
    w7_result = evaluate_warrant7(traffic_df, major_lanes, minor_lanes, speed, population,
                                  correctable_crashes, alternatives_tried)
    w8_result = evaluate_warrant8(network_continuity, route_designation, future_volumes)
    w9_result = evaluate_warrant9(railroad_crossing, train_frequency, queuing_distance, preemption_needed)

    def get_status(result):
        if result is None or result.get('met') is None:
            return '—'
        elif result.get('met'):
            return '✓ MET'
        else:
            return '✗ NOT MET'

    w1_status = get_status(w1_result)
    w2_status = get_status(w2_result)
    w3_status = get_status(w3_result)
    w4_status = get_status(w4_result)
    w5_status = get_status(w5_result)
    w6_status = get_status(w6_result)
    w7_status = get_status(w7_result)
    w8_status = get_status(w8_result)
    w9_status = get_status(w9_result)

    # Build display strings
    w1_threshold = w1_data = w1_notes = '—'
    w2_threshold = w2_data = w2_notes = '—'
    w3_threshold = w3_data = w3_notes = '—'
    w4_threshold = w4_data = w4_notes = '—'
    w5_threshold = w5_data = w5_notes = '—'
    w6_threshold = w6_data = w6_notes = '—'
    w7_threshold = w7_data = w7_notes = '—'
    w8_threshold = w8_data = w8_notes = '—'
    w9_threshold = w9_data = w9_notes = '—'

    if w1_result and w1_result.get('threshold_used'):
        thresh = w1_result['threshold_used']
        w1_threshold = f"{thresh['condition_a'][0]}/{thresh['condition_a'][1]} vph ({thresh['pct']}%)"
        w1_data = f"{w1_result['hours_met']}/8 hours"
        w1_notes = w1_result.get('details', '')

    if w2_result and w2_result.get('curve_points'):
        w2_threshold = f"Curve ({w2_result['pct']}%)"
        w2_data = f"{w2_result['hours_met']}/4 hours"
        w2_notes = w2_result.get('details', '')

    if w3_result and w3_result.get('peak_hour'):
        w3_threshold = f"Curve ({w3_result['pct']}%)"
        w3_data = f"Peak: {w3_result['peak_hour']}"
        w3_notes = w3_result.get('details', '')

    if w4_result:
        w4_threshold = f"Curve ({w4_result.get('pct', '100')}%)"
        w4_data = f"{ped_peak} peak / {ped_4hr} 4-hr"
        w4_notes = w4_result.get('details', '')

    if w5_result:
        w5_threshold = f"Gaps < Period"
        w5_data = f"{school_children} children"
        w5_notes = w5_result.get('details', '')

    if w6_result:
        w6_threshold = "1000-2640 ft"
        w6_data = f"{signal_spacing} ft spacing"
        w6_notes = w6_result.get('details', '')

    if w7_result:
        w7_threshold = "≥5 crashes + 80% vol"
        w7_data = f"{correctable_crashes} crashes, {w7_result.get('hours_meeting_volume', 0)}/8 hrs"
        w7_notes = w7_result.get('details', '')

    if w8_result:
        w8_threshold = "Eng. judgment"
        w8_data = "Route + future vol"
        w8_notes = w8_result.get('details', '')

    if w9_result:
        w9_threshold = "≤140 ft to RR"
        w9_data = f"{queuing_distance} ft, {train_frequency} trains/day"
        w9_notes = w9_result.get('details', '')

    # Summary table

    st.subheader("Summary")

    results_df = pd.DataFrame({
        'Warrant': ['1. Eight-Hour Volume', '2. Four-Hour Volume', '3. Peak Hour',
                    '4. Pedestrian Volume', '5. School Crossing', '6. Coordinated System',
                    '7. Crash Experience', '8. Roadway Network', '9. Grade Crossing'],
        'Status': [w1_status, w2_status, w3_status, w4_status, w5_status,
                   w6_status, w7_status, w8_status, w9_status],
        'Data': [w1_data, w2_data, w3_data, w4_data, w5_data,
                 w6_data, w7_data, w8_data, w9_data],
        'Threshold': [w1_threshold, w2_threshold, w3_threshold, w4_threshold, w5_threshold,
                      w6_threshold, w7_threshold, w8_threshold, w9_threshold],
        'Notes': [w1_notes, w2_notes, w3_notes, w4_notes, w5_notes,
                  w6_notes, w7_notes, w8_notes, w9_notes]
    })

    st.table(results_df)

    # Count met warrants
    met_count = sum(1 for s in [w1_status, w2_status, w3_status, w4_status, w5_status,
                                w6_status, w7_status, w8_status, w9_status] if '✓' in s)
    if met_count > 0:
        st.success(f"🚦 **{met_count} warrant(s) satisfied** — Signal installation may be justified")
    else:
        st.warning("⚠️ **No warrants currently satisfied** — Additional data or conditions may be needed")

    # Export buttons
    st.markdown("---")
    st.subheader("📥 Export Reports")

    # Gather project info for exports
    project_info = {
        'project_name': st.session_state.get('project_name', ''),
        'location': st.session_state.get('location', ''),
        'street_1': st.session_state.get('street_1', ''),
        'street_2': st.session_state.get('street_2', ''),
        'approach_speed': speed,
        'population': population,
        'lanes_1': major_lanes,
        'lanes_2': minor_lanes,
        'dist_signal': dist_signal
    }

    warrant_results = {
        'w1': w1_result, 'w2': w2_result, 'w3': w3_result,
        'w4': w4_result, 'w5': w5_result, 'w6': w6_result,
        'w7': w7_result, 'w8': w8_result, 'w9': w9_result
    }

    export_col1, export_col2, export_col3 = st.columns(3)

    with export_col1:
        # PDF Export
        pdf_data = generate_pdf_report(results_df, traffic_df, project_info, warrant_results)
        project_name_clean = project_info.get('project_name', 'warrant_analysis').replace(' ',
                                                                                          '_') or 'warrant_analysis'
        st.download_button(
            label="📄 Download PDF Report",
            data=pdf_data,
            file_name=f"{project_name_clean}_report.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    with export_col2:
        # Excel Export
        excel_data = generate_excel_report(results_df, traffic_df, project_info)
        st.download_button(
            label="📊 Download Excel",
            data=excel_data,
            file_name=f"{project_name_clean}_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with export_col3:
        # CSV Export
        csv_data = generate_csv_report(results_df)
        st.download_button(
            label="📋 Download CSV",
            data=csv_data,
            file_name=f"{project_name_clean}_summary.csv",
            mime="text/csv",
            use_container_width=True
        )

    # Charts row 1: Warrant 1
    col1, col2 = st.columns(2)

    with col1:

        st.subheader("Warrant 1: Major Street Volume")

        if w1_result and w1_result.get('hourly_results'):
            hourly = w1_result['hourly_results']
            hours = [h['hour'] for h in hourly]
            major_vols = [h['major_vol'] for h in hourly]
            thresh_major = hourly[0]['thresh_a_major']

            colors = ['#4caf50' if v >= thresh_major else '#e74c3c' for v in major_vols]

            fig = go.Figure()
            fig.add_trace(go.Bar(x=hours, y=major_vols, marker_color=colors,
                                 name=f'Major ({w1_result.get("major_street", "Street 1")})'))
            fig.add_hline(y=thresh_major, line_dash="dash", line_color="#1e2a3a",
                          annotation_text=f"Threshold: {thresh_major} vph")
            fig.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                              yaxis_title="vph", xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Enter traffic data to see analysis")

    with col2:

        st.subheader("Warrant 1: Minor Street Volume")

        if w1_result and w1_result.get('hourly_results'):
            hourly = w1_result['hourly_results']
            hours = [h['hour'] for h in hourly]
            minor_vols = [h['minor_vol'] for h in hourly]
            thresh_minor = hourly[0]['thresh_a_minor']

            colors = ['#4caf50' if v >= thresh_minor else '#e74c3c' for v in minor_vols]

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=hours, y=minor_vols, marker_color=colors,
                                  name=f'Minor ({w1_result.get("minor_street", "Street 2")})'))
            fig2.add_hline(y=thresh_minor, line_dash="dash", line_color="#1e2a3a",
                           annotation_text=f"Threshold: {thresh_minor} vph")
            fig2.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                               yaxis_title="vph", xaxis_tickangle=-45)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.caption("Enter traffic data to see analysis")

    # Charts row 2: Warrant 2 and 3
    col3, col4 = st.columns(2)

    with col3:

        st.subheader("Warrant 2: Four-Hour Volume")

        if w2_result and w2_result.get('hourly_results'):
            hourly = w2_result['hourly_results']
            curve = w2_result['curve_points']

            fig3 = go.Figure()

            curve_x = [p[0] for p in curve]
            curve_y = [p[1] for p in curve]
            fig3.add_trace(go.Scatter(x=curve_x, y=curve_y, mode='lines',
                                      name=f'Threshold ({w2_result["pct"]}%)',
                                      line=dict(color='#1e2a3a', dash='dash')))

            for h in hourly:
                if h['major_vol'] > 0:
                    color = '#4caf50' if h['above_curve'] else '#e74c3c'
                    fig3.add_trace(go.Scatter(x=[h['major_vol']], y=[h['minor_vol']],
                                              mode='markers', marker=dict(size=10, color=color),
                                              name=h['hour'], showlegend=False))

            fig3.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                               xaxis_title="Major Street (vph)", yaxis_title="Minor Street (vph)")
            st.plotly_chart(fig3, use_container_width=True)
            st.caption(f"**{w2_result['hours_met']}/4 hours** above curve")
        else:
            st.caption("Enter traffic data to see analysis")

    with col4:

        st.subheader("Warrant 3: Peak Hour")

        if w3_result and w3_result.get('peak_hour'):
            curve = w3_result['curve_points']

            fig4 = go.Figure()

            curve_x = [p[0] for p in curve]
            curve_y = [p[1] for p in curve]
            fig4.add_trace(go.Scatter(x=curve_x, y=curve_y, mode='lines',
                                      name=f'Threshold ({w3_result["pct"]}%)',
                                      line=dict(color='#1e2a3a', dash='dash')))

            color = '#4caf50' if w3_result['met'] else '#e74c3c'
            fig4.add_trace(go.Scatter(x=[w3_result['peak_major']], y=[w3_result['peak_minor']],
                                      mode='markers', marker=dict(size=14, color=color, symbol='star'),
                                      name=f"Peak: {w3_result['peak_hour']}"))

            fig4.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                               xaxis_title="Major Street (vph)", yaxis_title="Minor Street (vph)")
            st.plotly_chart(fig4, use_container_width=True)
            st.caption(
                f"**Peak Hour:** {w3_result['peak_hour']} — {w3_result['peak_major']:.0f} / {w3_result['peak_minor']:.0f} vph")
        else:
            st.caption("Enter traffic data to see analysis")

    # Charts row 3: Warrant 4 and 5
    col5, col6 = st.columns(2)

    with col5:

        st.subheader("Warrant 4: Pedestrian Volume")

        if w4_result and w4_result.get('peak_hour_curve'):
            curve = w4_result['peak_hour_curve']

            fig5 = go.Figure()

            curve_x = [p[0] for p in curve]
            curve_y = [p[1] for p in curve]
            fig5.add_trace(go.Scatter(x=curve_x, y=curve_y, mode='lines',
                                      name=f'Peak Hr Threshold ({w4_result["pct"]}%)',
                                      line=dict(color='#1e2a3a', dash='dash')))

            if traffic_df is not None and len(traffic_df) > 0:
                street1_total = traffic_df['Street 1 (vph)'].sum()
                street2_total = traffic_df['Street 2 (vph)'].sum()
                major_col = 'Street 1 (vph)' if street1_total >= street2_total else 'Street 2 (vph)'
                peak_major = traffic_df[major_col].max()

                color = '#4caf50' if w4_result.get('peak_hour_met') else '#e74c3c'
                fig5.add_trace(go.Scatter(x=[peak_major], y=[ped_peak],
                                          mode='markers', marker=dict(size=14, color=color, symbol='star'),
                                          name=f"Peak: {ped_peak} peds"))

            fig5.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                               xaxis_title="Major Street (vph)", yaxis_title="Pedestrians/Hour")
            st.plotly_chart(fig5, use_container_width=True)

            gap_status = "✓" if gaps < 60 else "✗"
            st.caption(f"**Gaps:** {gaps}/hr {gap_status} (need < 60)  |  **Distance:** {dist_signal} ft")
        else:
            st.caption("Enter pedestrian data to see analysis")

    with col6:

        st.subheader("Warrant 5: School Crossing")

        if school_crossing:
            fig6 = go.Figure()

            fig6.add_trace(go.Bar(
                x=['Schoolchildren', 'Adequate Gaps'],
                y=[school_children, school_gaps],
                marker_color=['#4caf50' if school_children >= 20 else '#e74c3c',
                              '#4caf50' if school_gaps < 30 else '#e74c3c'],
                name='Actual'
            ))

            fig6.add_shape(type="line", x0=-0.5, x1=0.5, y0=20, y1=20,
                           line=dict(color="#1e2a3a", dash="dash"))
            fig6.add_shape(type="line", x0=0.5, x1=1.5, y0=30, y1=30,
                           line=dict(color="#1e2a3a", dash="dash"))

            fig6.add_annotation(x=0, y=22, text="Min: 20", showarrow=False, font=dict(size=10))
            fig6.add_annotation(x=1, y=32, text="Max: 30", showarrow=False, font=dict(size=10))

            fig6.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                               yaxis_title="Count", showlegend=False)
            st.plotly_chart(fig6, use_container_width=True)
            st.caption(
                f"**Children:** {school_children} (min 20)  |  **Gaps:** {school_gaps} (must be < crossing period)")
        else:
            st.caption("Enable school crossing in Pedestrian/Bike section")

    # Charts row 4: Warrant 7
    col7, col8 = st.columns(2)

    with col7:

        st.subheader("Warrant 7: Crash Experience")

        if w7_result and w7_result.get('hourly_results'):
            hourly = w7_result['hourly_results']

            fig7 = go.Figure()

            # Plot 80% Warrant 1 threshold line (Condition A)
            thresh_a = w7_result['thresh_a_80']
            fig7.add_hline(y=thresh_a[1], line_dash="dash", line_color="#1e2a3a",
                           annotation_text=f"80% W1-A Minor: {thresh_a[1]} vph")

            # Plot hourly data points
            for h in hourly:
                if h['major_vol'] > 0:
                    color = '#4caf50' if h['meets_volume'] else '#e74c3c'
                    fig7.add_trace(go.Scatter(x=[h['major_vol']], y=[h['minor_vol']],
                                              mode='markers', marker=dict(size=10, color=color),
                                              name=h['hour'], showlegend=False,
                                              hovertemplate=f"{h['hour']}<br>Major: {h['major_vol']}<br>Minor: {h['minor_vol']}"))

            fig7.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                               xaxis_title="Major Street (vph)", yaxis_title="Minor Street (vph)")
            st.plotly_chart(fig7, use_container_width=True)

            cond_a = "✓" if w7_result.get('condition_a') else "✗"
            cond_b = "✓" if w7_result.get('condition_b') else "✗"
            cond_c = "✓" if w7_result.get('condition_c') else "✗"
            st.caption(f"**Conditions:** A (alternatives) {cond_a} | B (crashes) {cond_b} | C (volume) {cond_c}")
        else:
            # Show crash summary even without traffic data
            fig7 = go.Figure()

            fig7.add_trace(go.Bar(
                x=['Correctable Crashes'],
                y=[correctable_crashes],
                marker_color='#4caf50' if correctable_crashes >= 5 else '#e74c3c',
                name='Crashes'
            ))

            fig7.add_shape(type="line", x0=-0.5, x1=0.5, y0=5, y1=5,
                           line=dict(color="#1e2a3a", dash="dash"))
            fig7.add_annotation(x=0, y=5.5, text="Min: 5", showarrow=False, font=dict(size=10))

            fig7.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                               yaxis_title="Count (12-month)", showlegend=False)
            st.plotly_chart(fig7, use_container_width=True)

            alt_status = "✓" if alternatives_tried else "✗"
            st.caption(f"**Crashes:** {correctable_crashes}/5 required | **Alternatives tried:** {alt_status}")

    with col8:

        st.subheader("Warrants 6, 8, 9: Engineering Judgment")

        # Summary of engineering judgment warrants
        fig8 = go.Figure()

        warrant_names = ['W6: Coordinated', 'W8: Network', 'W9: Grade Xing']
        warrant_values = [1 if coordinated_system else 0,
                          1 if (network_continuity and route_designation) else 0,
                          1 if (railroad_crossing and queuing_distance <= 140) else 0]
        warrant_colors = ['#4caf50' if v else '#e0e0e0' for v in warrant_values]

        fig8.add_trace(go.Bar(
            x=warrant_names,
            y=[1, 1, 1],  # All same height
            marker_color=warrant_colors,
            text=['Active' if v else 'N/A' for v in warrant_values],
            textposition='inside'
        ))

        fig8.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=40),
                           yaxis_visible=False, showlegend=False)
        st.plotly_chart(fig8, use_container_width=True)

        st.caption("Green = Conditions present for evaluation | Configure in Network/Coordination tab")


# Route to appropriate page
if st.session_state.current_page == "Project Details":
    render_project_details()
elif st.session_state.current_page == "Traffic Counts":
    render_traffic_counts()
elif st.session_state.current_page == "Pedestrian/Bike":
    render_pedestrian_bike()
elif st.session_state.current_page == "Crash Data":
    render_crash_data()
elif st.session_state.current_page == "Network/Coordination":
    render_network_coordination()
elif st.session_state.current_page == "About":
    render_settings()

st.markdown("---")
render_results()