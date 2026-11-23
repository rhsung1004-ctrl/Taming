using System;
using UnityEngine;

namespace Necro.EditorTools
{
    // 월드 데이터 격자 → 지형 타일 배열 변환 (Tools/WorldGen/SPEC.md 의 행·열 방향 그대로).
    // Unity 엔진 기능(Mathf 등)을 쓰지 않는 순수 계산이라 Unity 밖에서도 시험할 수 있다.
    //
    // 방향 약속
    //  - height.r16: 행 = Z (남 → 북), 열 = X (서 → 동). heights[행 * heightRes + 열]
    //  - splat/detail PNG 를 GetPixels32 로 읽은 배열: 행 0 = 아래 줄 = 남쪽 (PNG 맨 윗줄 = 북쪽). px[행 * 너비 + 열]
    //  - TerrainData.SetHeights / SetAlphamaps / SetDetailLayer 의 배열: [y, x] = [Z 방향, X 방향]
    public static class NecroWorldGrid
    {
        static float Clamp(float v, float a, float b) { return v < a ? a : v > b ? b : v; }
        static float Lerp(float a, float b, float t) { return a + (b - a) * t; }

        // 지형 높이 (m): 높이 격자를 쌍선형 보간. 격자점 i 는 x = i / (heightRes − 1) × size
        public static float HeightAt(ushort[] heights, int heightRes, float size, float height, float x, float z)
        {
            float fx = Clamp(x / size * (heightRes - 1), 0f, heightRes - 1);
            float fz = Clamp(z / size * (heightRes - 1), 0f, heightRes - 1);
            int x0 = Math.Min((int)fx, heightRes - 2), z0 = Math.Min((int)fz, heightRes - 2);
            float tx = fx - x0, tz = fz - z0;
            float h00 = heights[z0 * heightRes + x0], h10 = heights[z0 * heightRes + x0 + 1];
            float h01 = heights[(z0 + 1) * heightRes + x0], h11 = heights[(z0 + 1) * heightRes + x0 + 1];
            return Lerp(Lerp(h00, h10, tx), Lerp(h01, h11, tx), tz) / 65535f * height;
        }

        // 타일 (tx, tz) 의 높이 배열 [행 = Z, 열 = X], 0~1. 이웃 타일과 가장자리 한 줄을 공유한다
        public static float[,] TileHeights(ushort[] heights, int heightRes, int tiles, int tx, int tz)
        {
            int res = (heightRes - 1) / tiles + 1;
            var h = new float[res, res];
            for (int r = 0; r < res; r++)
            {
                int row = (tz * (res - 1) + r) * heightRes + tx * (res - 1);
                for (int c = 0; c < res; c++) h[r, c] = heights[row + c] / 65535f;
            }
            return h;
        }

        public static int Channel(Color32 c, int ch) { return ch == 0 ? c.r : ch == 1 ? c.g : ch == 2 ? c.b : c.a; }

        // 층 무게 [행 = Z, 열 = X, 층]. 지형 알파맵 텍셀 j 는 타일 가장자리에서 j / (res − 1) 위치에 있다
        // (URP TerrainLitPasses.hlsl: splatUV = (uv × (텍셀 수 − 1) + 0.5) / 텍셀 수).
        // 전체 splat 그림(픽셀 i 중심 = (i + 0.5) × 텍셀 크기)을 그 위치에서 쌍선형으로 읽어 이웃 타일과 가장자리가 정확히 맞게 한다.
        public static float[,,] TileAlphamaps(Color32[] splat0, Color32[] splat1, int layers, int splatRes, float size, int tiles, int tx, int tz, int res)
        {
            int W = splatRes;
            var maps = new float[res, res, layers];
            float tileSize = size / tiles;
            float texel = size / W;
            var wts = new float[layers];
            for (int r = 0; r < res; r++)
            {
                float worldZ = tz * tileSize + r * tileSize / (res - 1);
                float fz = Clamp(worldZ / texel - 0.5f, 0f, W - 1);
                int z0 = (int)fz, z1 = Math.Min(z0 + 1, W - 1);
                float vz = fz - z0;
                for (int c = 0; c < res; c++)
                {
                    float worldX = tx * tileSize + c * tileSize / (res - 1);
                    float fx = Clamp(worldX / texel - 0.5f, 0f, W - 1);
                    int x0 = (int)fx, x1 = Math.Min(x0 + 1, W - 1);
                    float vx = fx - x0;
                    int i00 = z0 * W + x0, i10 = z0 * W + x1, i01 = z1 * W + x0, i11 = z1 * W + x1;
                    float w00 = (1 - vx) * (1 - vz), w10 = vx * (1 - vz), w01 = (1 - vx) * vz, w11 = vx * vz;
                    float sum = 0f;
                    for (int l = 0; l < layers; l++)
                    {
                        var px = l < 4 ? splat0 : splat1;
                        int ch = l & 3;
                        float v = Channel(px[i00], ch) * w00 + Channel(px[i10], ch) * w10 + Channel(px[i01], ch) * w01 + Channel(px[i11], ch) * w11;
                        wts[l] = v;
                        sum += v;
                    }
                    if (sum < 0.5f) { maps[r, c, 0] = 1f; continue; }       // 무게가 없으면 첫 층
                    for (int l = 0; l < layers; l++) maps[r, c, l] = wts[l] / sum;
                }
            }
            return maps;
        }

        // 풀 포기 수 [행 = Z, 열 = X]. 칸 하나 = 전체 detail 그림의 픽셀 하나 (1m).
        // 0~255 → 칸당 0~maxPerCell 개. 소수 부분은 칸마다 다른 해시로 올림/내림해 옅은 곳도 고르게 이어진다
        public static int[,] TileDetails(Color32[] px, int channel, int detailRes, int tiles, int tx, int tz, float maxPerCell, int seed, out long sum)
        {
            int res = detailRes / tiles;
            var d = new int[res, res];
            sum = 0;
            for (int r = 0; r < res; r++)
            {
                int gz = tz * res + r;
                for (int c = 0; c < res; c++)
                {
                    int gx = tx * res + c;
                    int v = Channel(px[gz * detailRes + gx], channel);
                    if (v == 0) continue;
                    float expect = v / 255f * maxPerCell;
                    int count = (int)Math.Floor(expect + Hash01(gx, gz, seed));
                    if (count < 0) count = 0;
                    if (count > 255) count = 255;
                    d[r, c] = count;
                    sum += count;
                }
            }
            return d;
        }

        // 0 이상 1 미만의 결정적 해시 (칸마다 고정)
        public static float Hash01(int x, int z, int k)
        {
            unchecked
            {
                uint h = (uint)x * 73856093u ^ (uint)z * 19349663u ^ (uint)(k + 1) * 83492791u;
                h ^= h >> 13; h *= 0x5bd1e995u; h ^= h >> 15;
                return (h & 0xFFFFFF) / 16777216f;
            }
        }

        // 지형 나무 위치 (타일 안 0~1 정규화). y 는 지형 높이에서 sink 를 뺀 값을 지형 높이로 나눈 것
        public static void TreeTile(float x, float z, float size, int tiles, out int tx, out int tz, out float nx, out float nz)
        {
            float tileSize = size / tiles;
            tx = Math.Min((int)(x / tileSize), tiles - 1);
            tz = Math.Min((int)(z / tileSize), tiles - 1);
            nx = (x - tx * tileSize) / tileSize;
            nz = (z - tz * tileSize) / tileSize;
        }
    }
}
