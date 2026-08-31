#ifndef _BUDDY_DATA_H_
#define _BUDDY_DATA_H_

#include <stdbool.h>
#include <stdint.h>

#define BUDDY_MAX_ROWS 6
#define BUDDY_TEXT_LEN 25
#define BUDDY_RELAY_TIMEOUT_MS 15000u

typedef struct {
    char text[BUDDY_TEXT_LEN];
    uint32_t color;
} BuddyRow;

typedef enum {
    BUDDY_CLOCK_STYLE_ARCS = 0,
    BUDDY_CLOCK_STYLE_DOTS = 1,
    BUDDY_CLOCK_STYLE_DOTTED_ARCS = 2,
} BuddyClockStyle;

#define BUDDY_CLOCK_STYLE_DEFAULT BUDDY_CLOCK_STYLE_DOTTED_ARCS

void BuddyData_Init(void);
void BuddyData_SetRow(int index, uint32_t color, const char *text);
const BuddyRow *BuddyData_GetRow(int index);
void BuddyData_SetClock(int hour, int minute, int second);
bool BuddyData_GetClockMilliseconds(uint32_t *milliseconds_since_midnight);
void BuddyData_SetClockStyle(BuddyClockStyle style);
BuddyClockStyle BuddyData_GetClockStyle(void);
void BuddyData_SetAlert(bool active);
bool BuddyData_IsAlertActive(void);
void BuddyData_RecordRelayHeartbeat(void);
bool BuddyData_IsRelayOnline(void);

#endif
