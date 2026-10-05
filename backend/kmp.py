def prefix_table(pat:str)->list[int]:
    table=[0]*len(pat)
    l=0
    # Build the prefix/suffix table
    for ind in range(1,len(pat)):
        while l and pat[ind]!=pat[l]:
            l=table[l-1]
        if pat[ind]==pat[l]:
            l+=1
        table[ind]=l
    return table

def find_all(text:str,pat:str)->list[int]:
    if not pat:
        return []
    table=prefix_table(pat)
    matches=[]
    matched=0
    # KMP skips characters we've already checked
    for ind,char in enumerate(text):
        while matched and char!=pat[matched]:
            matched=table[matched-1]
        if char==pat[matched]:
            matched+=1
        if matched==len(pat):
            matches.append(ind-len(pat)+1)
            matched=table[matched-1]
    return matches
