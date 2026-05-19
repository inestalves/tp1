import pandas as pd
import argparse
from datetime import timedelta
import os
from collections import defaultdict
import time


class Trajectory:
    def __init__(self, person_id, first_event):
        self.person_id = person_id
        self.visits = []
        self.current_visit = None
        self.last_ts = first_event['timestamp']
        self.last_zone = first_event['zone_id']
        self.gender = first_event['gender']
        self.age = first_event['age_range']

    def add_event(self, row):
        etype, ts, zid = row['event_type'], row['timestamp'], row['zone_id']

        if etype == 'entry':
            if not self.current_visit:
                self.current_visit = {'zone_id': zid, 'entry_time': ts, 'exit_time': None, 'dwell_s': 0}
        elif etype == 'linger' and self.current_visit and self.current_visit['zone_id'] == zid:
            self.current_visit['dwell_s'] = max(self.current_visit['dwell_s'], int(row['duration_s']))
        elif etype == 'exit' and self.current_visit and self.current_visit['zone_id'] == zid:
            self.current_visit['exit_time'] = ts
            self.close_current_visit(ts)
        self.last_ts, self.last_zone = ts, zid

    def close_current_visit(self, last_known_ts):
        if self.current_visit:
            if self.current_visit['exit_time'] is None:
                self.current_visit['exit_time'] = self.current_visit['entry_time'] + timedelta(
                    seconds=self.current_visit['dwell_s'])
            if self.current_visit['exit_time'] < self.current_visit['entry_time']:
                self.current_visit['exit_time'] = self.current_visit['entry_time']
            self.visits.append(self.current_visit)
            self.current_visit = None


def process_events(df):
    active_pools = defaultdict(list)
    person_count = 0
    final_trajectories = []
    df = df.sort_values('timestamp')

    for _, row in df.iterrows():
        current_ts = row['timestamp']
        attr_key = (row['gender'], row['age_range'])
        found_match = None
        pool = active_pools[attr_key]

        for i in range(len(pool) - 1, -1, -1):
            traj = pool[i]
            gap = (current_ts - traj.last_ts).total_seconds()
            if gap > 300:
                traj.close_current_visit(traj.last_ts)
                final_trajectories.append(pool.pop(i))
                continue

            if traj.current_visit:
                if traj.current_visit['zone_id'] == row['zone_id']:
                    found_match = traj
                    break
                else:
                    continue
            else:
                if gap >= 0:
                    found_match = traj
                    break

        if row['event_type'] == 'entry' and found_match:
            if current_ts == found_match.last_ts and row['zone_id'] == found_match.last_zone:
                found_match = None
        if found_match:
            found_match.add_event(row)
        else:
            person_count += 1
            new_traj = Trajectory(f"P_{person_count:05d}", row)
            new_traj.add_event(row)
            active_pools[attr_key].append(new_traj)

    for pool in active_pools.values():
        for traj in pool:
            traj.close_current_visit(traj.last_ts)
            final_trajectories.append(traj)

    all_visits = []
    for traj in final_trajectories:
        for v in traj.visits:
            v.update({
                'person_id': traj.person_id, 'gender': traj.gender, 'age_range': traj.age,
                'visit_date': v['entry_time'].strftime('%Y-%m-%d'),
                'hour_of_day': v['entry_time'].hour
            })
            all_visits.append(v)
    return all_visits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='data/events.csv')
    parser.add_argument('--output', default='output/journeys.csv')
    args = parser.parse_args()
    if not os.path.exists('output'): os.makedirs('output')

    df = pd.read_csv(args.input)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    print(f"A processar {len(df)} eventos...")
    visits = process_events(df)

    cols = [
        'person_id', 'zone_id', 'entry_time', 'exit_time', 'dwell_s',
        'gender', 'age_range', 'visit_date', 'hour_of_day'
    ]
    output_df = pd.DataFrame(visits)[cols].sort_values(['person_id', 'entry_time'])
    output_df.to_csv(args.output, index=False)
    print(f"Total de visitas: {len(output_df)} | Total de Pessoas: {output_df['person_id'].nunique()}")


if __name__ == "__main__":
    main()