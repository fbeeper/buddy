#ifndef _BUDDY_PROTOCOL_H_
#define _BUDDY_PROTOCOL_H_

#include <stdbool.h>

// Harness-agnostic USB CDC input accepted from the relay:
//   ROW <index 0-5> <rrggbb> <text...>
//   CLOCK <hour 0-23> <minute 0-59> <second 0-59>
//   PING
//   CSTYLE <arcs|dots|dotted-arcs>
//   ALERT <0|1>
//
// Parsing lives here; durable/renderable state lives in BuddyData.
void Buddy_Init(void);
bool Buddy_Poll(void);

#endif
