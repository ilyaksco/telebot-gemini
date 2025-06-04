def ensure_valid_markdown(text: str) -> str:
    """
    Ensures that basic markdown tags (*, `, ~, ```) are balanced in the given text.
    This is a simplified balancing mechanism.
    """
    if not text: 
        return ""

    stack = []
    result = []
    i = 0
    
    single_char_symbols = {'*', '`', '~'}
    multi_char_symbols = {'```'} 

    while i < len(text):
        matched_multi = False
        
        for symbol in multi_char_symbols:
            if text[i:i + len(symbol)] == symbol:
                if stack and stack[-1] == symbol:  
                    stack.pop()
                else:  
                    stack.append(symbol)
                result.append(symbol)
                i += len(symbol)
                matched_multi = True
                break

        if matched_multi:
            continue

        
        char = text[i]
        if char in single_char_symbols:
            if stack and stack[-1] == char: 
                stack.pop()
            else:  
                stack.append(char)
            result.append(char)
            i += 1
        else:
            
            result.append(char)
            i += 1

    while stack:
        unmatched_tag = stack.pop()
        result.append(unmatched_tag)

    return ''.join(result)
