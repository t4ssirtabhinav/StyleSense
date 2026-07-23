import { fetchUserFirstName } from '../../../features/home/home.service';

const mockMaybeSingle = jest.fn();
const mockEq = jest.fn();
const mockSelect = jest.fn();
const mockFrom = jest.fn();

mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
mockSelect.mockReturnValue({ eq: mockEq });
mockFrom.mockReturnValue({ select: mockSelect });

jest.mock('../../../lib/supabase', () => ({
  supabase: {
    from: (arg: unknown) => mockFrom(arg),
  },
}));

describe('fetchUserFirstName', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
    mockSelect.mockReturnValue({ eq: mockEq });
    mockFrom.mockReturnValue({ select: mockSelect });
  });

  it('selects full_name from users, filtered by eq(id, userId)', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: { full_name: 'Priya Sharma' },
      error: null,
    });

    await expect(fetchUserFirstName('user-1')).resolves.toBe('Priya Sharma');
    expect(mockFrom).toHaveBeenCalledWith('users');
    expect(mockSelect).toHaveBeenCalledWith('full_name');
    expect(mockEq).toHaveBeenCalledWith('id', 'user-1');
  });

  it('resolves null (not throw) when the row is missing', async () => {
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    await expect(fetchUserFirstName('user-2')).resolves.toBeNull();
  });

  it('resolves null (not throw) when the query errors', async () => {
    mockMaybeSingle.mockRejectedValue(new Error('network error'));

    await expect(fetchUserFirstName('user-3')).resolves.toBeNull();
  });
});
