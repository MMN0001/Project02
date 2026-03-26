#include <stdio.h>
#define N 200

int A[N][N], B[N][N], C[N][N];

int main() {
    for (int i=0;i<N;i++)
        for (int j=0;j<N;j++) {
            A[i][j]=i+j;
            B[i][j]=i-j;
        }

    for (int i=0;i<N;i++)
        for (int j=0;j<N;j++)
            for (int k=0;k<N;k++)
                C[i][j]+=A[i][k]*B[k][j];

    printf("%d\n", C[N-1][N-1]);
    return 0;
}