#include "BuddyProtocol.h"

#include "BuddyData.h"
#include "pico/stdlib.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BUDDY_LINE_MAX 64

static char line_buf[BUDDY_LINE_MAX];
static uint8_t line_len;

void Buddy_Init(void)
{
    BuddyData_Init();
    line_len = 0;
}

static bool handle_line(const char *line)
{
    char cmd[8];
    int consumed = 0;
    if (sscanf(line, "%7s%n", cmd, &consumed) < 1) return false;

    if (strcmp(cmd, "CLOCK") == 0) {
        int hour = -1, minute = -1, second = -1;
        if (sscanf(line + consumed, "%d %d %d", &hour, &minute, &second) < 3 ||
            hour < 0 || hour > 23 || minute < 0 || minute > 59 ||
            second < 0 || second > 59) return false;
        BuddyData_SetClock(hour, minute, second);
        printf("Buddy: clock %d:%d:%d\r\n", hour, minute, second);
        return true;
    }

    if (strcmp(cmd, "PING") == 0) return true;

    if (strcmp(cmd, "CSTYLE") == 0) {
        char style[16];
        BuddyClockStyle value;
        if (sscanf(line + consumed, "%15s", style) < 1) return false;
        if (strcmp(style, "arcs") == 0) value = BUDDY_CLOCK_STYLE_ARCS;
        else if (strcmp(style, "dots") == 0) value = BUDDY_CLOCK_STYLE_DOTS;
        else if (strcmp(style, "dotted-arcs") == 0)
            value = BUDDY_CLOCK_STYLE_DOTTED_ARCS;
        else return false;
        BuddyData_SetClockStyle(value);
        printf("Buddy: clock style %s\r\n", style);
        return true;
    }

    if (strcmp(cmd, "ALERT") == 0) {
        int enabled = -1;
        if (sscanf(line + consumed, "%d", &enabled) < 1 ||
            (enabled != 0 && enabled != 1)) return false;
        BuddyData_SetAlert(enabled == 1);
        printf("Buddy: alert %d\r\n", enabled);
        return true;
    }

    if (strcmp(cmd, "ROW") != 0) return false;

    int index = -1, index_consumed = 0;
    if (sscanf(line + consumed, "%d%n", &index, &index_consumed) < 1 ||
        index < 0 || index >= BUDDY_MAX_ROWS) return false;
    consumed += index_consumed;

    char color_str[8];
    int color_consumed = 0;
    if (sscanf(line + consumed, "%7s%n", color_str, &color_consumed) < 1)
        return false;
    char *end = NULL;
    uint32_t color = (uint32_t)strtoul(color_str, &end, 16);
    if (end == color_str) return false;

    const char *text = line + consumed + color_consumed;
    while (*text == ' ') text++;
    BuddyData_SetRow(index, color, text);
    printf("Buddy: row %d -> %s\r\n", index, text);
    return true;
}

bool Buddy_Poll(void)
{
    bool changed = false;
    int c;
    while ((c = getchar_timeout_us(0)) != PICO_ERROR_TIMEOUT) {
        if (c == '\n' || c == '\r') {
            if (line_len > 0) {
                line_buf[line_len] = '\0';
                if (handle_line(line_buf)) {
                    BuddyData_RecordRelayHeartbeat();
                    changed = true;
                }
                line_len = 0;
            }
        } else if (line_len < BUDDY_LINE_MAX - 1) {
            line_buf[line_len++] = (char)c;
        } else {
            line_len = 0;
        }
    }
    return changed;
}
