#include "mem.h"

#include <stddef.h>
#include <linux/limits.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

// translate a virtual address to a physical one via /proc/self/pagemap
uintptr_t virt_to_phys(void* virt) {
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
