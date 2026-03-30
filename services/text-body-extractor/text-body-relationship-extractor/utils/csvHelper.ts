
export const downloadCsv = (data: Record<string, any>[], filename: string): void => {
  if (data.length === 0) {
    console.warn('No data to download.');
    return;
  }

  const headers = Object.keys(data[0]);
  const csvRows = [
    headers.join(','), // header row
    ...data.map(row =>
      headers.map(fieldName => {
        const value = row[fieldName];
        // Handle values that might contain commas
        const escaped = ('' + value).includes(',') ? `"${value}"` : value;
        return escaped;
      }).join(',')
    ),
  ];

  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};
