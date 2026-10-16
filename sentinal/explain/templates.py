"""Safe plain and technical renderers."""
def render(card, mode: str = 'plain') -> str:
    mode = mode if mode in {'plain', 'technical'} else 'plain'
    lines = [card.what, 'Why: ' + '; '.join(card.why)]
    lines.append(f'Confidence: {card.confidence:.0%}')
    if card.evidence: lines.append('Evidence: ' + '; '.join(str(x) for x in card.evidence))
    if card.data_gaps: lines.append('Data gaps: ' + ', '.join(card.data_gaps))
    if card.next_steps: lines.append('Next steps: ' + '; '.join(card.next_steps))
    if mode == 'technical': lines.append('Factors: ' + repr(dict(card.factors)) + f' (weights {card.weights_version})')
    return '\n'.join(lines)
