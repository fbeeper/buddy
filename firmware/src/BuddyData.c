#include "BuddyData.h"

#include "pico/stdlib.h"
#include <string.h>

static BuddyRow rows[BUDDY_MAX_ROWS];
static bool clock_valid;
static uint32_t clock_anchor_ms_since_midnight;
static uint32_t clock_anchor_boot_ms;
static BuddyClockStyle clock_style;
static bool alert_active;
static uint32_t last_relay_heartbeat_ms;

static void safe_bounded_copy(char *dst, const char *src, size_t dst_size)
{
    size_t len = strlen(src);
    if (len > dst_size - 1) len = dst_size - 1;
    memcpy(dst, src, len);
    dst[len] = '\0';
}

void BuddyData_Init(void)
{
    memset(rows, 0, sizeof(rows));
    clock_valid = false;
    clock_style = BUDDY_CLOCK_STYLE_DEFAULT;
    alert_active = false;
    last_relay_heartbeat_ms = to_ms_since_boot(get_absolute_time());
}

void BuddyData_SetRow(int index, uint32_t color, const char *text)
{
    if (index < 0 || index >= BUDDY_MAX_ROWS || text == NULL) return;
    safe_bounded_copy(rows[index].text, text, sizeof(rows[index].text));
    rows[index].color = color;
}

const BuddyRow *BuddyData_GetRow(int index)
{
    if (index < 0 || index >= BUDDY_MAX_ROWS) return NULL;
    return &rows[index];
}

void BuddyData_SetClock(int hour, int minute, int second)
{
    clock_anchor_ms_since_midnight =
        (uint32_t)((hour * 3600 + minute * 60 + second) * 1000);
    clock_anchor_boot_ms = to_ms_since_boot(get_absolute_time());
    clock_valid = true;
}

bool BuddyData_GetClockMilliseconds(uint32_t *milliseconds_since_midnight)
{
    if (!clock_valid || milliseconds_since_midnight == NULL) return false;
    uint32_t elapsed_ms =
        to_ms_since_boot(get_absolute_time()) - clock_anchor_boot_ms;
    *milliseconds_since_midnight =
        (clock_anchor_ms_since_midnight + elapsed_ms) % 86400000u;
    return true;
}

void BuddyData_SetClockStyle(BuddyClockStyle style) { clock_style = style; }
BuddyClockStyle BuddyData_GetClockStyle(void) { return clock_style; }
void BuddyData_SetAlert(bool active) { alert_active = active; }
bool BuddyData_IsAlertActive(void) { return alert_active; }

void BuddyData_RecordRelayHeartbeat(void)
{
    last_relay_heartbeat_ms = to_ms_since_boot(get_absolute_time());
}

bool BuddyData_IsRelayOnline(void)
{
    uint32_t now_ms = to_ms_since_boot(get_absolute_time());
    return now_ms - last_relay_heartbeat_ms <= BUDDY_RELAY_TIMEOUT_MS;
}
