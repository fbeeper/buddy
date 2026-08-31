#include "BuddyMain.h"

#include "BuddyClock.h"
#include "BuddyPictureTile.h"
#include "BuddyStatusTile.h"
#include "BuddyUI.h"
#include <math.h>

static lv_disp_draw_buf_t disp_buf;
static lv_color_t buf0[BUDDY_DISPLAY_WIDTH * BUDDY_DISPLAY_HEIGHT / 2];
static lv_color_t buf1[BUDDY_DISPLAY_WIDTH * BUDDY_DISPLAY_HEIGHT / 2];
static lv_disp_drv_t disp_drv;
static lv_disp_t *lvgl_display;
static struct repeating_timer lvgl_timer;

static lv_obj_t *tileview;
static uint32_t current_tile_row;
static bool buddy_tile_latched;

#define ORIENT_VERTICAL_ANGLE_DEG 65.0f
#define ORIENT_STABLE_MS 250u
#define ORIENT_FILTER_ALPHA 0.15f
#define ROTATION_STABLE_MS 250u

static float filtered_angle_deg = -1.0f;
static uint32_t candidate_since_ms;
static bool have_candidate;
static uint32_t last_orientation_poll_ms;
static lv_disp_rot_t current_display_rotation;
static lv_disp_rot_t candidate_display_rotation;
static uint32_t rotation_candidate_since_ms;
static bool have_rotation_candidate;

static void disp_flush_cb(lv_disp_drv_t *disp, const lv_area_t *area,
                          lv_color_t *color_p);
static void dma_handler(void);
static bool repeating_lvgl_timer_callback(struct repeating_timer *timer);
static lv_disp_rot_t display_rotation_for_accel(float acc_x, float acc_y);

void LVGL_Init(void)
{
    add_repeating_timer_ms(5, repeating_lvgl_timer_callback, NULL, &lvgl_timer);
    lv_init();
    lv_disp_draw_buf_init(&disp_buf, buf0, buf1,
                          BUDDY_DISPLAY_WIDTH * BUDDY_DISPLAY_HEIGHT / 2);
    lv_disp_drv_init(&disp_drv);
    disp_drv.flush_cb = disp_flush_cb;
    disp_drv.draw_buf = &disp_buf;
    disp_drv.hor_res = BUDDY_DISPLAY_WIDTH;
    disp_drv.ver_res = BUDDY_DISPLAY_HEIGHT;
    disp_drv.sw_rotate = 1;
    lvgl_display = lv_disp_drv_register(&disp_drv);

    dma_channel_set_irq0_enabled(dma_tx, true);
    irq_set_exclusive_handler(DMA_IRQ_0, dma_handler);
    irq_set_enabled(DMA_IRQ_0, true);
}

void Widgets_Init(void)
{
    lv_obj_set_style_bg_color(lv_scr_act(), lv_color_black(), 0);
    lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, 0);

    tileview = lv_tileview_create(lv_scr_act());
    lv_obj_set_style_bg_color(tileview, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(tileview, LV_OPA_COVER, 0);
    lv_obj_set_scrollbar_mode(tileview, LV_SCROLLBAR_MODE_OFF);

    current_tile_row = 0;
    buddy_tile_latched = false;
    filtered_angle_deg = -1.0f;
    have_candidate = false;
    current_display_rotation = LV_DISP_ROT_NONE;
    have_rotation_candidate = false;

    BuddyPictureTile_Create(tileview);
    lv_obj_t *status_tile = BuddyStatusTile_Create(tileview);
    BuddyClock_Create(status_tile);
    lv_obj_set_tile_id(tileview, 0, current_tile_row, LV_ANIM_OFF);
}

void Widgets_PollOrientation(void)
{
    uint32_t now_ms = to_ms_since_boot(get_absolute_time());
    if (now_ms - last_orientation_poll_ms < 50) return;
    last_orientation_poll_ms = now_ms;

    float acc[3], gyro[3];
    unsigned int tim_count = 0;
    QMI8658_read_xyz(acc, gyro, &tim_count);

    float magnitude =
        sqrtf(acc[0] * acc[0] + acc[1] * acc[1] + acc[2] * acc[2]);
    if (magnitude < 1.0f) return;

    float cos_angle = fabsf(acc[2]) / magnitude;
    if (cos_angle > 1.0f) cos_angle = 1.0f;
    float raw_angle_deg = acosf(cos_angle) * (180.0f / 3.14159265f);
    if (filtered_angle_deg < 0.0f) {
        filtered_angle_deg = raw_angle_deg;
    } else {
        filtered_angle_deg +=
            ORIENT_FILTER_ALPHA * (raw_angle_deg - filtered_angle_deg);
    }

    if (filtered_angle_deg < ORIENT_VERTICAL_ANGLE_DEG) {
        if (!buddy_tile_latched) have_candidate = false;
        have_rotation_candidate = false;
        return;
    }

    lv_disp_rot_t target_rotation = display_rotation_for_accel(acc[0], acc[1]);
    if (target_rotation == current_display_rotation) {
        have_rotation_candidate = false;
    } else if (!have_rotation_candidate ||
               target_rotation != candidate_display_rotation) {
        candidate_display_rotation = target_rotation;
        rotation_candidate_since_ms = now_ms;
        have_rotation_candidate = true;
    } else if (now_ms - rotation_candidate_since_ms >= ROTATION_STABLE_MS) {
        current_display_rotation = target_rotation;
        lv_disp_set_rotation(lvgl_display, current_display_rotation);
        have_rotation_candidate = false;
    }

    if (buddy_tile_latched) return;
    if (!have_candidate) {
        have_candidate = true;
        candidate_since_ms = now_ms;
        return;
    }
    if (now_ms - candidate_since_ms >= ORIENT_STABLE_MS) {
        current_tile_row = 1;
        buddy_tile_latched = true;
        lv_obj_set_tile_id(tileview, 0, current_tile_row, LV_ANIM_ON);
        have_candidate = false;
    }
}

static lv_disp_rot_t display_rotation_for_accel(float acc_x, float acc_y)
{
    if (fabsf(acc_x) > fabsf(acc_y))
        return acc_x < 0.0f ? LV_DISP_ROT_NONE : LV_DISP_ROT_180;
    return acc_y >= 0.0f ? LV_DISP_ROT_90 : LV_DISP_ROT_270;
}

static void disp_flush_cb(lv_disp_drv_t *disp, const lv_area_t *area,
                          lv_color_t *color_p)
{
    (void)disp;
    LCD_1IN28_SetWindows(area->x1, area->y1, area->x2, area->y2);
    dma_channel_configure(
        dma_tx, &c, &spi_get_hw(LCD_SPI_PORT)->dr, color_p,
        ((area->x2 + 1 - area->x1) * (area->y2 + 1 - area->y1)) * 2, true);
}

static void dma_handler(void)
{
    if (dma_channel_get_irq0_status(dma_tx)) {
        dma_channel_acknowledge_irq0(dma_tx);
        lv_disp_flush_ready(&disp_drv);
    }
}

static bool repeating_lvgl_timer_callback(struct repeating_timer *timer)
{
    (void)timer;
    lv_tick_inc(5);
    return true;
}
