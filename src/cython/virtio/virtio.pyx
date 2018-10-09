from libc.stdint cimport uintptr_t, uint32_t, uint8_t, uint16_t, uint64_t

cdef floor(val, align):
  return val & ~(align-1)

cdef ceil(val, align):
  return floor(val + align-1, align)

cdef struct vring_desc:
  uint16_t addr
  uint32_t len
  uint16_t flags
  uint16_t next

cdef struct vring_avail:
  uint16_t flags
  uint32_t idx
  uint16_t ring[0]

cdef struct vring_used_elem:
  uint32_t id
  uint32_t len

cdef struct vring_used:
  uint16_t flags
  uint16_t idx
  vring_used_elem ring[0]

cdef struct vring:
  uint32_t num
  vring_desc* desc
  vring_avail* avail
  vring_used* used


cdef class VRing:
  cdef vring _ring

  def __cinit__(self, num, mem):
    pass
    self._ring = vring(num=num,
                       desc=<vring_desc*>mem,
                       avail=<vring_avail*>(mem[num * sizeof(vring_desc)]),
                       used=<vring_used*>(mem[virtq_size(num)-sizeof(vring_used)-num*sizeof(vring_used_elem)-1]))

cdef align(x):
  return (x + 4096) & ~4096

cdef virtq_size(size):
  return align(sizeof(vring_desc)*size + sizeof(uint16_t)*(3 + size)) + align(sizeof(uint16_t)*3 + sizeof(vring_used_elem)*size)

# static inline void virtio_legacy_vring_init(struct vring* vr, unsigned int num, uint8_t* p, unsigned long align) {
# 	vr->num = num;
# 	vr->desc = (struct vring_desc*)p;
# 	vr->avail = (struct vring_avail*)(p + num * sizeof(struct vring_desc));
# 	vr->used = (void*)RTE_ALIGN_CEIL((uintptr_t)(&vr->avail->ring[num]), align);
# }

#define RTE_PTR_ADD(ptr, x) ((void*)((uintptr_t)(ptr) + (x)))
#define RTE_ALIGN_FLOOR(val, align) (typeof(val))((val) & (~((typeof(val))((align)-1))))
#define RTE_ALIGN_CEIL(val, align) RTE_ALIGN_FLOOR(((val) + ((typeof(val))(align)-1)), align)
#define RTE_PTR_ALIGN_FLOOR(ptr, align) ((typeof(ptr))RTE_ALIGN_FLOOR((uintptr_t)ptr, align))
#define RTE_PTR_ALIGN_CEIL(ptr, align) RTE_PTR_ALIGN_FLOOR((typeof(ptr))RTE_PTR_ADD(ptr, (align)-1), align)
