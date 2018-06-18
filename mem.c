#include "mem.h"

#include <stddef.h>
#include <linux/limits.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

// translate a virtual address to a physical one via /proc/self/pagemap
static uintptr_t virt_to_phys(void* virt) {
	long pagesize = sysconf(_SC_PAGESIZE);
	int fd = open("/proc/self/pagemap", O_RDONLY);
	// pagemap is an array of pointers for each normal-sized page
	lseek(fd, (uintptr_t) virt / pagesize * sizeof(uintptr_t), SEEK_SET);
	uintptr_t phy = 0;
	read(fd, &phy, sizeof(phy));
	close(fd);
	if (!phy) {
		// error("failed to translate virtual address %p to physical address", virt);
	}
	// bits 0-54 are the page number
	return (phy & 0x7fffffffffffffULL) * pagesize + ((uintptr_t) virt) % pagesize;
}

static uint32_t huge_pg_id;

// allocate memory suitable for DMA access in huge pages
// this requires hugetlbfs to be mounted at /mnt/huge
// not using anonymous hugepages because hugetlbfs can give us multiple pages with contiguous virtual addresses
// allocating anonymous pages would require manual remapping which is more annoying than handling files
struct dma_memory memory_allocate_dma(size_t size, bool require_contiguous) {
	// round up to multiples of 2 MB if necessary, this is the wasteful part
	// this could be fixed by co-locating allocations on the same page until a request would be too large
	// when fixing this: make sure to align on 128 byte boundaries (82599 dma requirement)
	if (size % HUGE_PAGE_SIZE) {
		size = ((size >> HUGE_PAGE_BITS) + 1) << HUGE_PAGE_BITS;
	}
	if (require_contiguous && size > HUGE_PAGE_SIZE) {
		// this is the place to implement larger contiguous physical mappings if that's ever needed
		// error("could not map physically contiguous memory");
	}
	// unique filename, C11 stdatomic.h requires a too recent gcc, we want to support gcc 4.8
	uint32_t id = __sync_fetch_and_add(&huge_pg_id, 1);
	char path[PATH_MAX];
	snprintf(path, PATH_MAX, "/mnt/huge/ixy-%d-%d", getpid(), id);
	// temporary file, will be deleted to prevent leaks of persistent pages
	int fd = open(path, O_CREAT | O_RDWR, S_IRWXU);
	ftruncate(fd, (off_t) size);
	void* virt_addr = (void*) mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_HUGETLB, fd, 0);
	// never swap out DMA memory
	mlock(virt_addr, size);
	// don't keep it around in the hugetlbfs
	close(fd);
	unlink(path);

	return (struct dma_memory) {
		.virt = virt_addr,
		.phy = virt_to_phys(virt_addr)
	};
}
