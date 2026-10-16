import time
# Builds a table that helps us skip unnecessary comparisons while matching the pattern.
def prefix_table(pattern):
    table=[0]*len(pattern)
    matched=0

    for ind in range(1,len(pattern)):
        while matched and pattern[ind]!=pattern[matched]:
            matched=table[matched-1]
        if pattern[ind]==pattern[matched]:
            matched+=1
        table[ind]=matched
    return table


# Finds all starting positions where the pattern appears in the text.
def find_all(text:str,pattern:str,comparison_capacity:int|None=None)->list[int]:
    if not pattern:
        return []
    if comparison_capacity is not None and comparison_capacity<1:
        raise ValueError("Comparison capacity must be positive")

    table=prefix_table(pattern)
    matches=[]
    matched=0
    chars_since_pause=0

    for ind,char in enumerate(text):
        while matched and char!=pattern[matched]:
            matched=table[matched-1]
        if char==pattern[matched]:
            matched+=1
        if matched==len(pattern):
            matches.append(ind-len(pattern)+1)
            matched=table[matched-1]

        if comparison_capacity is not None:
            chars_since_pause+=1
            if chars_since_pause==comparison_capacity:
                time.sleep(1)
                chars_since_pause=0

    return matches
