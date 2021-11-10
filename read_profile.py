import pstats

p = pstats.Stats("profiling.txt")
p.sort_stats("cumulative").print_stats(1000)
