/* Compatibility shim for glibc 2.35 — defines __isoc23_strtol/
 * symbols that ONNX Runtime (compiled against glibc 2.38+) expects.
 * These are functionally identical to the C11 versions on older glibc. */
#define _GNU_SOURCE
#include <stdlib.h>

long long __isoc23_strtoll(const char *nptr, char **endptr, int base) {
  return strtoll(nptr, endptr, base);
}

unsigned long long __isoc23_strtoull(const char *nptr, char **endptr, int base) {
  return strtoull(nptr, endptr, base);
}

long __isoc23_strtol(const char *nptr, char **endptr, int base) {
  return strtol(nptr, endptr, base);
}
