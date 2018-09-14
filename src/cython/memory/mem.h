#ifndef IXY_MEMORY_H
#define IXY_MEMORY_H

#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <stddef.h>
#include <assert.h>

#define HUGE_PAGE_BITS 21
#define HUGE_PAGE_SIZE (1 << HUGE_PAGE_BITS)
#define SIZE_PKT_BUF_HEADROOM 40

uintptr_t virt_to_phys(void* virt);

#endif //IXY_MEMORY_H
