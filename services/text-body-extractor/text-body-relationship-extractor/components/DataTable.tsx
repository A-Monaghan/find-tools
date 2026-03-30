
import React from 'react';

interface DataTableProps {
  headers: string[];
  data: (string | number)[][];
}

const DataTable: React.FC<DataTableProps> = ({ headers, data }) => {
  if (data.length === 0) {
    return <p className="text-slate-500 text-sm italic text-center py-4">No data available.</p>;
  }

  return (
    <div className="overflow-x-auto custom-scrollbar">
      <table className="min-w-full divide-y divide-white/5">
        <thead className="bg-[#0f172a]/80">
          <tr>
            {headers.map((header, index) => (
              <th
                key={index}
                scope="col"
                className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-widest text-slate-500"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {data.map((row, rowIndex) => (
            <tr key={rowIndex} className="hover:bg-white/[0.02] transition-colors">
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="px-4 py-3 whitespace-nowrap text-sm text-slate-200"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default DataTable;
