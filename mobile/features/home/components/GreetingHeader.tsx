import { Text } from '../../../components/ui';
import { useAuthStore } from '../../auth/auth.store';
import { useUserGreetingQuery } from '../home.queries';

// Time-of-day boundaries computed in IST (Asia/Kolkata), per CLAUDE.md's
// India-specific rule — never device-local time, which may differ for a
// traveling user.
function getISTHour(): number {
  const formatter = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    hourCycle: 'h23',
  });
  return Number(formatter.format(new Date()));
}

export function getTimeOfDayGreeting(hour: number): string {
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

// First word of full_name, matching Avatar.tsx's own getInitials precedent
// of splitting on whitespace.
export function getFirstName(
  fullName: string | null | undefined,
): string | undefined {
  if (!fullName) return undefined;
  const [first] = fullName.trim().split(/\s+/).filter(Boolean);
  return first || undefined;
}

// Renders the time-of-day greeting + name (or a generic no-name fallback).
// Never renders undefined/blank interpolation, never blocks on the network
// call — a loading/error/null greeting query all resolve to the same
// no-name variant (this is decorative personalization, not a form/
// transaction; BL-007 does not apply, there's no error surface here).
export function GreetingHeader() {
  const session = useAuthStore((state) => state.session);
  const userId = session?.user.id;
  const greetingQuery = useUserGreetingQuery(userId);

  const timeGreeting = getTimeOfDayGreeting(getISTHour());
  const firstName = greetingQuery.isSuccess
    ? getFirstName(greetingQuery.data)
    : undefined;

  const fullGreeting = firstName
    ? `${timeGreeting}, ${firstName}!`
    : `${timeGreeting}!`;

  return (
    <Text testID="greeting-header" variant="display" className="mx-md mt-md">
      {fullGreeting}
    </Text>
  );
}
