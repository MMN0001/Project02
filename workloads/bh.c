#include <stdio.h>
#include <stdlib.h>
#define N 1000000

int main() {
    int sum = 0;

    for (int i = 0; i < N; i++) {
        if (rand() % 2)
            sum += i;
        else
            sum -= i;
    }

    printf("%d\n", sum);
    return 0;
}