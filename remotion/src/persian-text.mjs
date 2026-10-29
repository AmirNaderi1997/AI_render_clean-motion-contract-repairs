// Keep this display-only rule in sync with engine.persian_text.display_text.
export const displayText = text => {
  let previousLatin = false;
  return String(text || '').replace(/\S+/g, value => {
    const latin = /[A-Za-z]/.test(value);
    const result = latin || previousLatin || !/[0-9]/.test(value) ? value : value.replace(/[0-9%.]/g, c => c === '%' ? '٪' : c === '.' ? '٫' : '۰۱۲۳۴۵۶۷۸۹'[Number(c)]);
    previousLatin = latin;
    return result;
  });
};

export const displayUnits = text => {
  const units = [], run = [];
  for (const word of displayText(text).split(/\s+/).filter(Boolean)) {
    if (/^[A-Za-z0-9][A-Za-z0-9.,:+_/%-]*$/.test(word)) run.push(word);
    else {
      if (run.length) units.push(run.splice(0).join(' '));
      units.push(word);
    }
  }
  if (run.length) units.push(run.join(' '));
  return units;
};
