#ifndef _BUDDY_STATUS_TILE_H_
#define _BUDDY_STATUS_TILE_H_

#include "lvgl.h"

lv_obj_t *BuddyStatusTile_Create(lv_obj_t *tileview);
void BuddyStatusTile_Refresh(void);
void BuddyStatusTile_UpdateRelayStatus(void);
void BuddyStatusTile_UpdateBacklight(void);

#endif
