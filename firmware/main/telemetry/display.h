// ========================================
// 3.5" ILI9488 DISPLAY (SPI, 480 x 320 LANDSCAPE)
// ========================================
//
// Just enough to draw a status screen: filled rectangles and big block text
// from a built-in 5x7 font. Colours are 0xRRGGBB.

#pragma once

#include <stdbool.h>
#include <stdint.h>

#define DISPLAY_WIDTH   480
#define DISPLAY_HEIGHT  320

void display_init(void);
void display_backlight(bool on);

void display_fill(int x, int y, int w, int h, uint32_t color);

// Draws text with its background filled, so it overwrites what was there.
// Each character is 6*scale wide and 8*scale tall.
void display_text(int x, int y, const char *text, int scale, uint32_t fg, uint32_t bg);
int  display_text_width(const char *text, int scale);
