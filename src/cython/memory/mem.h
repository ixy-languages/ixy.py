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

struct dma_memory {
	void* virt;
	uintptr_t phy;
};

struct dma_memory memory_allocate_dma(size_t size, bool require_contiguous);

#endif //IXY_MEMORY_H
