#include <stdio.h>
#define N 1000000

int main() {
    static int a[N], b[N], c[N];
    for (int i = 0; i < N; i++) {
        a[i] = i;
        b[i] = i * 2;
    }
    for (int i = 0; i < N; i++) {
        c[i] = a[i] + b[i];
    }
    printf("%d\n", c[N-1]);
    return 0;
}