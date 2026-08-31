#include "BuddyClock.h"

#include "BuddyData.h"
#include "BuddyUI.h"
#include "pico/stdlib.h"
#include <math.h>

#define CLOCK_INDICATOR_THICKNESS 6
#define CLOCK_INDICATOR_GAP 4
#define HOUR_TRACK_COLOR 0x8020B3u
#define MINUTE_TRACK_COLOR 0xFE1961u
#define SECOND_TRACK_COLOR 0xDF5A3Au
#define HOUR_DOT_ACTIVE_COLOR 0xB62DFFu
#define HOUR_DOT_BRIGHTNESS_PERCENT 50u
#define MINUTE_DOT_BRIGHTNESS_PERCENT 25u
#define CLOCK_DOT_THICKNESS CLOCK_INDICATOR_THICKNESS
#define HOUR_DOT_COUNT 12
#define MINUTE_DOT_COUNT 60

static lv_obj_t *clock_parent;
static lv_obj_t *hour_arc;
static lv_obj_t *minute_arc;
static lv_obj_t *second_dot;
static uint32_t last_update_ms;
static BuddyClockStyle rendered_style;
static bool style_initialized;
static int last_dot_hour;
static int last_dot_minute;

static uint32_t dim_rgb888(uint32_t color, uint32_t percent)
{
    uint32_t red = ((color >> 16) & 0xFFu) * percent / 100u;
    uint32_t green = ((color >> 8) & 0xFFu) * percent / 100u;
    uint32_t blue = (color & 0xFFu) * percent / 100u;
    return (red << 16) | (green << 8) | blue;
}

static lv_obj_t *create_arc(lv_obj_t *parent, int size, int width,
                            uint32_t color, int maximum)
{
    lv_obj_t *arc = lv_arc_create(parent);
    lv_obj_set_size(arc, size, size);
    lv_obj_align(arc, LV_ALIGN_CENTER, 0, 0);
    lv_arc_set_rotation(arc, 270);
    lv_arc_set_bg_angles(arc, 0, 360);
    lv_arc_set_range(arc, 0, maximum);
    lv_arc_set_value(arc, 0);
    lv_obj_set_style_arc_width(arc, 0, LV_PART_MAIN);
    lv_obj_set_style_arc_opa(arc, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_arc_width(arc, width, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(arc, lv_color_hex(color), LV_PART_INDICATOR);
    lv_obj_set_style_arc_rounded(arc, true, LV_PART_INDICATOR);
    lv_obj_remove_style(arc, NULL, LV_PART_KNOB);
    lv_obj_clear_flag(arc, LV_OBJ_FLAG_CLICKABLE);
    return arc;
}

// Mirrors LVGL 8.1's private rounded-arc cap placement without allocating an
// object per marker.
static void get_arc_cap_area(uint16_t angle, lv_coord_t outer_radius,
                             uint8_t thickness, lv_area_t *area)
{
    const uint8_t precision_shift = 8;
    const uint8_t pixel_center_adjust = 127;
    const int32_t half_thickness = thickness / 2;
    const uint8_t even_width_correction = (thickness & 1u) ? 0u : 1u;
    int32_t cap_x = ((outer_radius - half_thickness)
                     * lv_trigo_sin(90 - angle))
                    >> (LV_TRIGO_SHIFT - precision_shift);
    int32_t cap_y = ((outer_radius - half_thickness) * lv_trigo_sin(angle))
                    >> (LV_TRIGO_SHIFT - precision_shift);

    if (cap_x > 0) {
        cap_x = (cap_x - pixel_center_adjust) >> precision_shift;
        area->x1 = cap_x - half_thickness + even_width_correction;
        area->x2 = cap_x + half_thickness;
    } else {
        cap_x = (cap_x + pixel_center_adjust) >> precision_shift;
        area->x1 = cap_x - half_thickness;
        area->x2 = cap_x + half_thickness - even_width_correction;
    }
    if (cap_y > 0) {
        cap_y = (cap_y - pixel_center_adjust) >> precision_shift;
        area->y1 = cap_y - half_thickness + even_width_correction;
        area->y2 = cap_y + half_thickness;
    } else {
        cap_y = (cap_y + pixel_center_adjust) >> precision_shift;
        area->y1 = cap_y - half_thickness;
        area->y2 = cap_y + half_thickness - even_width_correction;
    }
}

static void draw_dot_set(int count, int active_index, lv_coord_t outer_radius,
                         lv_coord_t center_x, lv_coord_t center_y,
                         uint32_t track_color, uint32_t active_color,
                         uint32_t brightness_percent,
                         const lv_area_t *clip_area)
{
    lv_draw_rect_dsc_t inactive;
    lv_draw_rect_dsc_init(&inactive);
    inactive.bg_color = lv_color_hex(dim_rgb888(track_color, brightness_percent));
    inactive.bg_opa = LV_OPA_COVER;
    inactive.radius = LV_RADIUS_CIRCLE;
    inactive.border_width = 0;
    lv_draw_rect_dsc_t active = inactive;
    active.bg_color = lv_color_hex(active_color);
    const lv_coord_t marker_radius = outer_radius
        - CLOCK_INDICATOR_THICKNESS / 2 + CLOCK_DOT_THICKNESS / 2;

    for (int i = 0; i < count; i++) {
        uint16_t angle = (uint16_t)((270 + (i * 360) / count) % 360);
        lv_area_t area;
        get_arc_cap_area(angle, marker_radius, CLOCK_DOT_THICKNESS, &area);
        area.x1 += center_x;
        area.x2 += center_x;
        area.y1 += center_y;
        area.y2 += center_y;
        if (area.x2 < clip_area->x1 || area.x1 > clip_area->x2 ||
            area.y2 < clip_area->y1 || area.y1 > clip_area->y2) continue;
        lv_draw_rect(&area, clip_area, i == active_index ? &active : &inactive);
    }
}

static void draw_dots_cb(lv_event_t *event)
{
    BuddyClockStyle style = BuddyData_GetClockStyle();
    if (style == BUDDY_CLOCK_STYLE_ARCS) return;
    uint32_t day_ms;
    if (!BuddyData_GetClockMilliseconds(&day_ms)) return;

    int active_hour = (int)((day_ms / 3600000u) % 12u);
    int active_minute = (int)((day_ms / 60000u) % 60u);
    if (style == BUDDY_CLOCK_STYLE_DOTTED_ARCS) {
        active_hour = -1;
        active_minute = -1;
    }

    const lv_area_t *clip = lv_event_get_clip_area(event);
    lv_area_t hour_area, minute_area;
    lv_obj_get_coords(hour_arc, &hour_area);
    lv_obj_get_coords(minute_arc, &minute_area);
    lv_coord_t hour_x = hour_area.x1 + lv_area_get_width(&hour_area) / 2;
    lv_coord_t hour_y = hour_area.y1 + lv_area_get_height(&hour_area) / 2;
    lv_coord_t minute_x = minute_area.x1 + lv_area_get_width(&minute_area) / 2;
    lv_coord_t minute_y = minute_area.y1 + lv_area_get_height(&minute_area) / 2;

    draw_dot_set(HOUR_DOT_COUNT, active_hour,
                 lv_area_get_width(&hour_area) / 2, hour_x, hour_y,
                 HOUR_TRACK_COLOR, HOUR_DOT_ACTIVE_COLOR,
                 HOUR_DOT_BRIGHTNESS_PERCENT, clip);
    draw_dot_set(MINUTE_DOT_COUNT, active_minute,
                 lv_area_get_width(&minute_area) / 2, minute_x, minute_y,
                 MINUTE_TRACK_COLOR, MINUTE_TRACK_COLOR,
                 MINUTE_DOT_BRIGHTNESS_PERCENT, clip);
}

void BuddyClock_Create(lv_obj_t *parent)
{
    clock_parent = parent;
    hour_arc = create_arc(parent, BUDDY_DISPLAY_WIDTH,
                          CLOCK_INDICATOR_THICKNESS, HOUR_TRACK_COLOR, 12000);
    minute_arc = create_arc(
        parent,
        BUDDY_DISPLAY_WIDTH - 2 * (CLOCK_INDICATOR_THICKNESS + CLOCK_INDICATOR_GAP),
        CLOCK_INDICATOR_THICKNESS, MINUTE_TRACK_COLOR, 3600);

    second_dot = lv_obj_create(parent);
    lv_obj_set_size(second_dot, CLOCK_INDICATOR_THICKNESS,
                    CLOCK_INDICATOR_THICKNESS);
    lv_obj_set_pos(second_dot,
                   (BUDDY_DISPLAY_WIDTH - CLOCK_INDICATOR_THICKNESS) / 2,
                   2 * (CLOCK_INDICATOR_THICKNESS + CLOCK_INDICATOR_GAP));
    lv_obj_set_style_radius(second_dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(second_dot, lv_color_hex(SECOND_TRACK_COLOR), 0);
    lv_obj_set_style_bg_opa(second_dot, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(second_dot, 0, 0);
    lv_obj_clear_flag(second_dot, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);

    lv_obj_add_event_cb(parent, draw_dots_cb, LV_EVENT_DRAW_MAIN, NULL);
    last_update_ms = 0;
    style_initialized = false;
    last_dot_hour = -1;
    last_dot_minute = -1;
}

void BuddyClock_Update(void)
{
    uint32_t now_ms = to_ms_since_boot(get_absolute_time());
    if (now_ms - last_update_ms < 50u) return;
    last_update_ms = now_ms;

    uint32_t day_ms;
    if (!BuddyData_GetClockMilliseconds(&day_ms)) return;
    uint32_t hour = (day_ms / 3600000u) % 12u;
    uint32_t minute = (day_ms / 60000u) % 60u;
    BuddyClockStyle style = BuddyData_GetClockStyle();

    if (!style_initialized || style != rendered_style) {
        rendered_style = style;
        style_initialized = true;
        if (style == BUDDY_CLOCK_STYLE_DOTS) {
            lv_obj_add_flag(hour_arc, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(minute_arc, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_obj_clear_flag(hour_arc, LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(minute_arc, LV_OBJ_FLAG_HIDDEN);
        }
        last_dot_hour = -1;
        last_dot_minute = -1;
        lv_obj_invalidate(clock_parent);
    }

    lv_arc_set_value(hour_arc, (int)(hour * 1000u));
    lv_arc_set_value(minute_arc, (int)(minute * 60u));
    if (style == BUDDY_CLOCK_STYLE_DOTS &&
        ((int)hour != last_dot_hour || (int)minute != last_dot_minute)) {
        last_dot_hour = (int)hour;
        last_dot_minute = (int)minute;
        lv_obj_invalidate(clock_parent);
    }

    uint32_t second = (day_ms / 1000u) % 60u;
    float angle = ((float)second / 60.0f) * 2.0f * 3.14159265f;
    const float center = (float)BUDDY_DISPLAY_WIDTH / 2.0f;
    const float dot_radius = (float)CLOCK_INDICATOR_THICKNESS / 2.0f;
    const float radius = center
        - 2.5f * (float)CLOCK_INDICATOR_THICKNESS
        - 2.0f * (float)CLOCK_INDICATOR_GAP;
    int x = (int)(center + radius * sinf(angle) - dot_radius);
    int y = (int)(center - radius * cosf(angle) - dot_radius);
    lv_obj_set_pos(second_dot, x, y);
}
